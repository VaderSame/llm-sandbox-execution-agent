import argparse
from utils import greet

def main():
    parser = argparse.ArgumentParser(description="A simple multi-file testing script.")
    parser.add_argument("--name", type=str, required=True, help="The name of the user to greet.")
    parser.add_argument("--count", type=int, default=1, help="Number of times to greet.")
    args = parser.parse_args()

    for i in range(args.count):
        print(f"[{i+1}/{args.count}] {greet(args.name)}")

if __name__ == "__main__":
    main()
