"""
Main entry point for the report generation program.
This script executes the report generation process and displays the computed statistics.
"""

from report import generate_report

if __name__ == "__main__":
    total_sum, average = generate_report()
    print(f"Sum: {total_sum}")
    print(f"Average: {average}")
    print(f"fuck U Rishabh, sike")