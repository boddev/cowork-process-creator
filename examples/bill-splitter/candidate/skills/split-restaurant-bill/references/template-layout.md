# Bill splitter sheet layout

Everything needed to reproduce the sheet without the original template file.
Cell references are the same whether you copy a supplied workbook or build a
new one, so the per-person block keeps working.

## Sheet

One sheet per meal, named for the meal label (for example the restaurant on
the receipt). When a template workbook is supplied, copy it and add the meal
sheet; leave the workbook's own `Template` and `Example` sheets untouched.
The original workbook is optional and is not bundled. Use an existing native
spreadsheet facility; do not install a library or claim the JSON helper
creates a workbook. If none is available, return only the computed summary
and explicitly report the missing workbook.

Excel sheet names must be 1-31 characters, cannot contain `: \ / ? * [ ]`,
and cannot start or end with an apostrophe. Suggest a valid shortened name
when needed and resolve existing-name collisions without replacing a sheet.
Keep the full meal label in `A1`. Write names and receipt labels as literal
text, never as formulas.

## Rows 1-2 — heading

- `A1`: the meal label.
- `A2`: how-to text: put each person's name in the header cells `E11:L11`,
  list every receipt line below, then enter how many SHARES of that line each
  person takes — 1 for an equal share, 2 for twice as much, blank for none.
  The line is divided by the shares claimed, and tax and tip follow each
  person's share of the food and drink.

## Rows 4-9 — bill totals

| Cell | Label (column A) | Column B |
|---|---|---|
| 5 | `Items subtotal ($)` | `=B32` |
| 6 | `Tax ($)` | typed: the tax printed on the receipt |
| 7 | `Tip (%)` | typed: the tip rate as a percentage-formatted fraction |
| 8 | `Tip ($)` | `=ROUND(B5*B7,2)` for a user-selected tip rate |
| 9 | `Grand total ($)` | `=B5+B6+B8` |

Column C on rows 6 and 7 holds the hint text ("Enter the tax amount printed on
the receipt", "Enter the tip rate you want to leave, e.g. 18.0%").

When using a printed gratuity **amount**, enter that exact amount in `B8` on
the new meal sheet and use `=IF(B5=0,0,B8/B5)` in `B7` to display its implied
rate. Label this as a fixed printed gratuity. This deliberate override preserves
the receipt's actual payment instead of recomputing it from a rounded rate.
Do not change the supplied workbook's original sheets. If the user later
chooses a rate-based tip, restore the rate-entry cell and rounded `B8` formula
above; do not create a circular reference.

## Rows 10-32 — itemized receipt

Row 10 is the banner: `ITEMIZED RECEIPT  -  under each name, enter how many
SHARES of the line that person takes`.

Row 11 headers: `A` `Item (list the line as printed)`, `B` `Line amount ($)`,
`C` `Shares claimed`, `D` `Cost per share ($)`, then one person per column
across `E11:L11` (eight columns maximum).

Rows 12-31 (twenty lines):

- `A`: the line as printed on the receipt.
- `B`: the line amount, typed.
- `C`: `=SUM(E12:L12)` — shares claimed.
- `D`: `=IF(C12=0,0,B12/C12)` — cost per share.
- `E12:L31`: whole numbers 0-99 or blank, one cell per person per line.
  The original template validates this range as a whole number 0-99, allowing
  blanks, with the prompt "Enter the quantity this person had of this line:
  1 for an equal share, 2 if they had two, blank if none."

Row 32: `A32` `Items total / shares claimed`, `B32` `=SUM(B12:B31)`,
`C32` `=SUM(C12:C31)`.

## Rows 34-46 — who owes what

Row 34 banner `WHO OWES WHAT`; row 36 headers `Person`, `Items ($)`,
`Tax share ($)`, `Tip share ($)`, `Total owed ($)`.

Rows 37-44, one per person column E..L (row 37 ↔ column E, row 44 ↔ column L):

| Column | Formula for row 37 |
|---|---|
| A | `=IF(E$11="","",E$11)` |
| B | `=SUMPRODUCT($D$12:$D$31,E$12:E$31)` |
| C | `=IF($B$5=0,0,B37/$B$5*$B$6)` |
| D | `=IF($B$5=0,0,B37/$B$5*$B$8)` |
| E | `=B37+C37+D37` |

Row 45: `A45` `Total collected`, with `=SUM(B37:B44)` across B..E.
Row 46: `A46` `Check vs grand total (should be 0)`, `E46` `=E45-B9`.

## Rounding note

The per-person formulas carry full precision and Excel rounds only for display,
so the displayed per-person totals can add up to more or less than the grand
total. The helper's reconciled figures are the authoritative amounts to quote
to the user; write them alongside the formulas (for example in the summary and
in a `G37:G44` column headed `Amount to pay ($)`) rather than deleting the
formulas. Label that column as a calculated snapshot, add `=SUM(G37:G44)` in
`G45` and `=ROUND(G45-B9,2)` in `G46`, and check that both totals reconcile.
Tell the user to re-run the helper and refresh the snapshot after changing
names, lines, shares, tax or tip. Editing formulas does not update these fixed
reconciled amounts automatically.

## Notes block (rows 48-55)

Reproduce these as the sheet's own guidance:

1. Blue cells are the ones you type in: person names, line amounts, shares, tax and tip.
2. A share is a portion of the line, not a physical item. One cake split three ways is 3 shares of 1 each, so each person pays a third.
3. Someone who had more takes more shares. A $28.00 line for four beers where one person drank two is 4 shares at $7.00, with 2 entered under that person.
4. Cost per share = line amount divided by the shares claimed on that row, so nobody pays for something they did not have.
5. Tax and tip are allocated by each person's share of the food and drink total, not split evenly.
6. Use the twenty receipt rows (12-31); this skill does not support additional rows or more than eight diners.
7. The check row should read $0.00 — if it does not, a line has no shares entered against it.

## Formats

Currency with two decimals for the amount columns (`B`, `D`, and `B`-`E` in
the per-person block), a percentage with one decimal for `B7`, plain whole
numbers for `C` and the share cells. Formatting is cosmetic; the figures and
formulas above are what must be right.
