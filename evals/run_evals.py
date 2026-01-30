#!/usr/bin/env python3
"""
Eval Runner for Personal Finance Agent

Runs test cases from test_cases.csv against the golden dataset
and validates the agent's responses.
"""

import os
import re
import csv
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Set up paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
EVALS_DIR = SCRIPT_DIR
TEST_CASES_PATH = EVALS_DIR / "test_cases.csv"
RESULTS_DIR = EVALS_DIR / "results"
GOLDEN_DATASET_PATH = os.environ.get('FINANCE_DB_PATH', str(EVALS_DIR / "golden_transactions.csv"))

# Ensure results directory exists
RESULTS_DIR.mkdir(exist_ok=True)

# Import agent after setting env var
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agent.agent import root_agent


class AnswerValidator:
    """Validates agent answers against expected values."""

    @staticmethod
    def strip_sql_blocks(text: str) -> str:
        """Remove SQL code blocks from text to avoid extracting numbers from SQL."""
        return re.sub(r'```(?:sql)?\s*.*?```', '', text, flags=re.DOTALL)

    @staticmethod
    def extract_number(text: str) -> Optional[float]:
        """Extract the most relevant number from text (handles $, commas).

        Priority order:
        1. Dollar amounts (e.g., $1,234.56)
        2. Numbers that aren't 4-digit years (2020-2030)
        3. Any remaining number
        """
        # Strip SQL code blocks first
        text = AnswerValidator.strip_sql_blocks(text)

        # Priority 1: Look for dollar amounts ($X,XXX.XX or $X.XX)
        dollar_matches = re.findall(r'-?\$[\d,]+\.?\d*', text)
        if dollar_matches:
            cleaned = dollar_matches[0].replace('$', '').replace(',', '')
            return float(cleaned)

        # Priority 2: Look for numbers that aren't years (2020-2030)
        text_clean = text.replace(',', '')
        all_matches = re.findall(r'-?\d+\.?\d*', text_clean)
        non_year_matches = [m for m in all_matches if not re.match(r'^20[2-3]\d$', m)]

        if non_year_matches:
            return float(non_year_matches[0])

        # Priority 3: Fall back to any number
        if all_matches:
            return float(all_matches[0])

        return None
    
    @staticmethod
    def validate_numeric(agent_answer: str, expected_value: str, tolerance: float) -> Dict[str, Any]:
        """Validate numeric answer within tolerance."""
        extracted = AnswerValidator.extract_number(agent_answer)
        expected = float(expected_value)
        
        if extracted is None:
            return {
                "passed": False,
                "error": "Could not extract number from answer",
                "extracted": None,
                "expected": expected
            }
        
        diff = abs(extracted - expected)
        passed = diff <= tolerance
        
        return {
            "passed": passed,
            "extracted": extracted,
            "expected": expected,
            "difference": diff,
            "tolerance": tolerance
        }
    
    @staticmethod
    def validate_count(agent_answer: str, expected_value: str) -> Dict[str, Any]:
        """Validate count (exact integer match)."""
        extracted = AnswerValidator.extract_number(agent_answer)
        expected = int(expected_value)
        
        if extracted is None:
            return {
                "passed": False,
                "error": "Could not extract count from answer",
                "extracted": None,
                "expected": expected
            }
        
        passed = int(extracted) == expected
        
        return {
            "passed": passed,
            "extracted": int(extracted),
            "expected": expected
        }
    
    @staticmethod
    def validate_contains(agent_answer: str, expected_value: str) -> Dict[str, Any]:
        """Validate that answer contains all expected items (semicolon-separated)."""
        expected_items = [item.strip() for item in expected_value.split(';')]
        answer_lower = agent_answer.lower()
        
        found_items = []
        missing_items = []
        
        for item in expected_items:
            if item.lower() in answer_lower:
                found_items.append(item)
            else:
                missing_items.append(item)
        
        passed = len(missing_items) == 0
        
        return {
            "passed": passed,
            "expected_items": expected_items,
            "found_items": found_items,
            "missing_items": missing_items
        }
    
    @staticmethod
    def validate_no_data(agent_answer: str) -> Dict[str, Any]:
        """Validate that answer indicates no data found."""
        no_data_phrases = [
            "no transactions",
            "no data",
            "didn't find",
            "did not find",
            "haven't",
            "don't have",
            "do not have",
            "not found",
            "no spending",
            "no records",
            "no results",
            "cannot find",
            "could not find",
            "no matching",
            "$0",
            "0.00",
        ]
        
        answer_lower = agent_answer.lower()
        found_phrases = [phrase for phrase in no_data_phrases if phrase in answer_lower]
        passed = len(found_phrases) > 0
        
        return {
            "passed": passed,
            "found_phrases": found_phrases,
            "checked_phrases": no_data_phrases
        }


class EvalRunner:
    """Runs evaluations on the finance agent."""
    
    APP_NAME = "finance_eval"
    USER_ID = "eval_user"
    DELAY_BETWEEN_TESTS = 5  # seconds between each test to avoid rate limits
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 10  # seconds, doubles on each retry

    def __init__(self):
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            app_name=self.APP_NAME,
            agent=root_agent,
            session_service=self.session_service,
        )
        self.validator = AnswerValidator()
        self.results = []
    
    def load_test_cases(self) -> List[Dict]:
        """Load test cases from CSV."""
        test_cases = []
        
        with open(TEST_CASES_PATH, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                test_cases.append(row)
        
        return test_cases
    
    async def run_agent(self, question: str) -> str:
        """Run agent with retry logic for rate limit errors."""
        for attempt in range(self.MAX_RETRIES):
            try:
                session = await self.session_service.create_session(
                    app_name=self.APP_NAME,
                    user_id=self.USER_ID,
                )

                message = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=question)],
                )

                # Collect all text parts from the final response
                text_parts = []
                async for event in self.runner.run_async(
                    user_id=self.USER_ID,
                    session_id=session.id,
                    new_message=message,
                ):
                    if not event.is_final_response():
                        continue
                    if not event.content or not event.content.parts:
                        continue
                    for part in event.content.parts:
                        # Skip function_call and function_response parts
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)

                return " ".join(text_parts) if text_parts else "No response from agent"
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    retry_delay = self.INITIAL_RETRY_DELAY * (2 ** attempt)
                    print(f"  Rate limited (attempt {attempt + 1}/{self.MAX_RETRIES}), waiting {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    continue
                return f"ERROR: {error_str}"

        return "ERROR: Max retries exceeded due to rate limiting"
    
    def validate_answer(self, agent_answer: str, test_case: Dict) -> Dict[str, Any]:
        """Validate agent answer against expected value."""
        answer_type = test_case['answer_type']
        expected_value = test_case['expected_value']
        
        if answer_type == 'numeric':
            tolerance = float(test_case['tolerance']) if test_case['tolerance'] else 0.01
            return self.validator.validate_numeric(agent_answer, expected_value, tolerance)
        
        elif answer_type == 'count':
            return self.validator.validate_count(agent_answer, expected_value)
        
        elif answer_type == 'contains':
            return self.validator.validate_contains(agent_answer, expected_value)
        
        elif answer_type == 'no_data':
            return self.validator.validate_no_data(agent_answer)
        
        else:
            return {
                "passed": False,
                "error": f"Unknown answer_type: {answer_type}"
            }
    
    async def run_single_test(self, test_case: Dict, test_num: int, total_tests: int) -> Dict:
        """Run a single test case."""
        question = test_case['question']

        print(f"\n{'='*80}")
        print(f"Test {test_num}/{total_tests}: {question}")
        print(f"{'='*80}")

        result = {
            "question": question,
            "expected_value": test_case['expected_value'],
            "answer_type": test_case['answer_type'],
            "notes": test_case['notes'],
            "timestamp": datetime.now().isoformat()
        }

        try:
            # Run agent
            print("Running agent...")
            agent_answer = await self.run_agent(question)
            result["agent_answer"] = agent_answer
            
            # Check for errors
            if agent_answer.startswith("ERROR:"):
                result["passed"] = False
                result["error"] = agent_answer
                print(f"❌ FAILED - Agent error")
                return result
            
            # Validate answer
            print("Validating answer...")
            validation = self.validate_answer(agent_answer, test_case)
            result["validation"] = validation
            result["passed"] = validation["passed"]
            
            # Print result
            if result["passed"]:
                print(f"✅ PASSED")
            else:
                print(f"❌ FAILED")
                print(f"Validation details: {validation}")
            
        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)
            result["agent_answer"] = None
            print(f"❌ FAILED - Exception: {str(e)}")
        
        return result
    
    async def run_all_tests(self) -> Dict:
        """Run all test cases and generate report."""
        print(f"\n{'#'*80}")
        print(f"STARTING EVAL RUN")
        print(f"{'#'*80}")
        print(f"Golden dataset: {GOLDEN_DATASET_PATH}")
        print(f"Test cases: {TEST_CASES_PATH}")

        # Load test cases
        test_cases = self.load_test_cases()
        total_tests = len(test_cases)
        print(f"Total test cases: {total_tests}")

        # Run each test with delay between tests to avoid rate limits
        results = []
        for i, test_case in enumerate(test_cases, 1):
            if i > 1:
                print(f"\n  Waiting {self.DELAY_BETWEEN_TESTS}s before next test...")
                await asyncio.sleep(self.DELAY_BETWEEN_TESTS)
            result = await self.run_single_test(test_case, i, total_tests)
            results.append(result)
        
        # Generate summary
        passed_tests = sum(1 for r in results if r["passed"])
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "golden_dataset": str(GOLDEN_DATASET_PATH),
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "pass_rate": round(pass_rate, 1),
            "results": results
        }
        
        # Save results
        self.save_results(summary)
        
        # Print summary
        self.print_summary(summary)
        
        return summary
    
    def save_results(self, summary: Dict):
        """Save results to JSON file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = RESULTS_DIR / f"eval_run_{timestamp}.json"
        
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n{'='*80}")
        print(f"Results saved to: {output_path}")
        print(f"{'='*80}")
    
    def print_summary(self, summary: Dict):
        """Print eval summary."""
        print(f"\n{'#'*80}")
        print(f"EVAL SUMMARY")
        print(f"{'#'*80}")
        print(f"Total Tests:  {summary['total_tests']}")
        print(f"Passed:       {summary['passed']} ✅")
        print(f"Failed:       {summary['failed']} ❌")
        print(f"Pass Rate:    {summary['pass_rate']}%")
        
        # Show failed tests
        if summary['failed'] > 0:
            print(f"\n{'='*80}")
            print("FAILED TESTS:")
            print(f"{'='*80}")
            
            for result in summary['results']:
                if not result['passed']:
                    print(f"\n❌ {result['question']}")
                    print(f"   Expected: {result['expected_value']}")
                    if 'agent_answer' in result and result['agent_answer']:
                        answer_preview = result['agent_answer'][:200]
                        print(f"   Answer: {answer_preview}{'...' if len(result['agent_answer']) > 200 else ''}")
                    if 'validation' in result:
                        print(f"   Validation: {result['validation']}")
                    if 'error' in result:
                        print(f"   Error: {result['error']}")


async def main():
    """Main entry point."""
    runner = EvalRunner()
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())