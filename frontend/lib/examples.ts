// Example bugs for the "Load example" menu. The error text of each one was produced by
// actually running the code in the backend sandbox (see backend/tests/fixtures/bugs.json).
export interface Example {
  id: string;
  label: string;
  code: string;
  error: string;
  expectedOutput: string;
}

export const EXAMPLES: Example[] = [
  {
    "id": "index_error_basic",
    "label": "IndexError: off-by-one loop",
    "code": "numbers = [1, 2, 3]\n\nfor i in range(len(numbers) + 1):\n    print(numbers[i])\n",
    "error": "Traceback (most recent call last):\n  File \"main.py\", line 4, in <module>\n    print(numbers[i])\n          ~~~~~~~^^^\nIndexError: list index out of range",
    "expectedOutput": "1\n2\n3"
  },
  {
    "id": "chained_two_bugs",
    "label": "Two bugs: first fix fails (retry demo)",
    "code": "marks = {\"name\": \"Asha\", \"scores\": [80, 90, 100]}\n\ntotal = 0\nfor i in range(len(marks[\"scores\"]) + 1):\n    total += marks[\"scores\"][i]\n\naverage = total / marks[\"count\"]\nprint(average)\n",
    "error": "Traceback (most recent call last):\n  File \"main.py\", line 5, in <module>\n    total += marks[\"scores\"][i]\n             ~~~~~~~~~~~~~~~^^^\nIndexError: list index out of range",
    "expectedOutput": "90.0"
  },
  {
    "id": "key_error_typo",
    "label": "KeyError: typo in a dictionary key",
    "code": "inventory = {\"apples\": 5, \"bananas\": 3}\ntotal = inventory[\"apples\"] + inventory[\"banana\"]\nprint(total)\n",
    "error": "Traceback (most recent call last):\n  File \"main.py\", line 2, in <module>\n    total = inventory[\"apples\"] + inventory[\"banana\"]\n                                  ~~~~~~~~~^^^^^^^^^^\nKeyError: 'banana'",
    "expectedOutput": "8"
  },
  {
    "id": "missing_return",
    "label": "TypeError: function forgot to return",
    "code": "def square(x):\n    result = x * x\n\nvalue = square(4)\nprint(value + 1)\n",
    "error": "Traceback (most recent call last):\n  File \"main.py\", line 5, in <module>\n    print(value + 1)\n          ~~~~~~^~~\nTypeError: unsupported operand type(s) for +: 'NoneType' and 'int'",
    "expectedOutput": "17"
  },
  {
    "id": "wrong_conditional_adult",
    "label": "Wrong output: > instead of >=",
    "code": "def is_adult(age):\n    # 18 and older counts as an adult\n    if age > 18:\n        return True\n    return False\n\nprint(is_adult(18))\nprint(is_adult(25))\n",
    "error": "Wrong output.\nExpected:\nTrue\nTrue\nActual:\nFalse\nTrue",
    "expectedOutput": "True\nTrue"
  },
  {
    "id": "infinite_loop_no_increment",
    "label": "Infinite loop: timeout",
    "code": "total = 0\ni = 1\nwhile i <= 5:\n    total += i\nprint(total)\n",
    "error": "Execution timed out after 5s (possible infinite loop or very slow code).",
    "expectedOutput": "15"
  }
];
