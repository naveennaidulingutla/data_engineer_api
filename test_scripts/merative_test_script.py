from test_scripts.test_agent import TestAgent, functionality_test
import pandas as pd
import os
from datetime import datetime
import json
import time
from test_scripts.test_utils import (
    load_test_cases,
    load_test_cases_csv,
    prepare_summary,
    update_summary,
    save_test_result,
    save_summary
)

datasource = "merative"
# lets get no_of_iters from python argument while running the script, default value is 2
import argparse
parser = argparse.ArgumentParser(description='Run MERATIVE test script with specified arguments.')
parser.add_argument('--no_of_iters', type=int, default=2, help='Number of iterations/sessions to run for each test case')
parser.add_argument('--exist_file_path', type=str, default=None, help='Path to an existing test results file (default: None, which creates a new file)')
parser.add_argument(
    '--question_ids',
    type=int,
    nargs='+',
    default=None,
    help='List of question IDs to run (e.g., --question_ids 1 3 5 to run Q1, Q3, and Q5)'
)
args = parser.parse_args()
no_of_iters = args.no_of_iters
exist_file_path = args.exist_file_path
question_ids = args.question_ids

# MERATIVE_TEST_CASES = load_test_cases('./test_scripts/merative_test_cases.xlsx')
MERATIVE_TEST_CASES = load_test_cases_csv('./test_scripts/merative_test_cases.csv') # you can switch to csv or excel test cases as needed
overall_start_time = datetime.now()

# exist_file_path = f'./test_scripts/test_reports/merative_test_results_20260313_153906.xlsx'
if exist_file_path and os.path.exists(exist_file_path):
    file_path = exist_file_path
    summary = pd.read_excel(file_path, sheet_name='summary').to_dict('list')
else:
    file_path = f"./test_scripts/test_reports/merative_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    summary = prepare_summary(no_of_iters)
print(f"Test results will be saved to: {file_path}")
if question_ids:
    MERATIVE_TEST_CASES_ = [MERATIVE_TEST_CASES[i] for i in range(len(MERATIVE_TEST_CASES)) if i+1 in question_ids]
else:
    MERATIVE_TEST_CASES_ = MERATIVE_TEST_CASES # run all test cases
for test_case in MERATIVE_TEST_CASES_:
    print(f"\nProcessing test case: {test_case}")
    try:
        question_number = MERATIVE_TEST_CASES.index(test_case) + 1
        test_case_id = f"Q{question_number}"
        print(f"Question: {test_case['Question']}")
        print(f"Expected SQL: {test_case['Expected SQL Query']}")
        start_time = datetime.now()
        functionality_test_results,run_time_per_session = functionality_test(
            test_case['Question'], datasource=datasource, no_of_iters=no_of_iters
        )

        retry_count = 0
        while retry_count < 3:
            final_output_ = TestAgent(datasource=datasource).run_test_case(
                test_case['Question'],
                test_case['Expected SQL Query'],
                results_from_sessions=functionality_test_results
            )
            if final_output_ and 'output' in final_output_ and final_output_['output']:
                try:
                    df = pd.DataFrame(json.loads(final_output_['output']))
                    break
                except json.JSONDecodeError:
                    print(f"Invalid JSON response. Retrying... ({retry_count + 1}/3)")
            else:
                print(f"Empty or invalid response. Retrying... ({retry_count + 1}/3)")
            retry_count += 1
            time.sleep(2)
    
        end_time = datetime.now()
        print(f"Time taken for test case '{test_case_id}': {end_time - start_time}")

        pass_count = df[df['status'] == 'PASS'].shape[0]
        fail_count = df[df['status'] == 'FAIL'].shape[0]
        df['run_time_per_session'] = run_time_per_session
        summary = update_summary(
            summary, test_case_id, no_of_iters, pass_count, fail_count, start_time, end_time
        )
        save_test_result(df, file_path, test_case_id)
    except Exception as e:
        print(f"An error occurred while processing test case '{test_case_id}': {str(e)}")

save_summary(summary, file_path)

overall_end_time = datetime.now()
print(f"Time taken for the entire test suite: {overall_end_time - overall_start_time} no.of test cases: {len(MERATIVE_TEST_CASES_)} no. of iterations per test case: {no_of_iters}")

# how to run this script:
#  python -m test_scripts.merative_test_script --no_of_iters 3 --exist_file_path ./test_scripts/test_reports/merative_test_results_20260313_153906.xlsx --question_ids 1 3 5
# This will run test cases Q1, Q3, and Q5 with 3 iterations
# ./test_scripts/test_reports/merative_test_results_20260317_215949.xlsx

# ./test_scripts/test_reports/merative_test_results_final_report.xlsx


# python -m test_scripts.merative_test_script --no_of_iters 2 --exist_file_path ./test_scripts/test_reports/merative_test_results_20260318_134710.xlsx