from pathlib import Path

APP = Path("app.py")

text = APP.read_text(encoding="utf-8")

old = '<div class="menu"><a href="/products"> Products</a><a href="/stock-in"> Stock In</a><a href="/stock-out"> Stock Out</a><a href="/cash"> Cash</a><a href="/history"> History</a></div>'

new = '<div class="menu"><a href="/products"> Products</a><a href="/stock-in"> Stock In</a><a href="/stock-out"> Stock Out</a><a href="/cash"> Cash</a><a href="/history"> History</a><a href="/debts"> Debts/Credit</a></div>'

if old not in text:
    print("ERROR: User menu was not found.")
    print("No changes were made.")
    raise SystemExit(1)

if '<a href="/debts"> Debts/Credit</a>' in text:
    print("Debts/Credit is already in the menu.")
    raise SystemExit(0)

text = text.replace(old, new, 1)

APP.write_text(text, encoding="utf-8")

print("==============================================")
print("       DEBTS MENU ADDED SUCCESSFULLY")
print("==============================================")
print("User menu now contains: Debts/Credit")
print("Existing menu items were preserved.")
print("==============================================")