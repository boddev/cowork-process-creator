---
name: split-restaurant-bill
description: "Split an itemized restaurant receipt among named diners and produce a bill-splitter workbook plus a per-person summary. Use when someone uploads or points at a restaurant receipt and asks who owes what, to split a bill, to work out shares of a meal, or to fill in a restaurant bill splitter sheet."
---
# Split a restaurant bill

Turn one itemized receipt into an amount owed per person. Each receipt line is
divided by the number of shares claimed against it, so nobody pays for
something they did not have, and tax and tip follow each person's share of the
food and drink subtotal rather than being split evenly.

Use only Cowork's existing native receipt-reading, file, Python 3.10+ and
spreadsheet facilities. Do not install packages or a runtime, call an external
OCR service, or automate a desktop. If receipt reading or Python execution is
unavailable, stop with that limitation. Spreadsheet creation is a separate
native step; the bundled helper writes JSON, not an XLSX workbook.

## Inputs

| Input | Required | Meaning |
|---|---|---|
| Receipt file | Yes | Image, PDF or text of the itemized receipt: each line, its amount, the subtotal, the tax, and any printed gratuity. |
| Diner names | Yes | The people splitting the bill, up to eight. Order sets the column order. |
| Who had what | No | Plain language, e.g. "Priya had two of the beers; the bread was for the table". If missing, ask (see Step 2). |
| Tip rate | No | A fraction such as 0.2, with at most six decimal places. If missing, take the gratuity printed on the receipt; if the receipt prints none, ask; only if the user explicitly declines to choose, disclose and use 18% (the template's own default). |
| Meal label | No | Used as the worksheet name and in the summary. Default: the restaurant name read from the receipt. |
| Output filename | No | Suggest a valid new filename based on the meal label and legible receipt date, e.g. `harbour-grill-2026-03-08-split.xlsx`. Ask if those details are missing. |
| Template workbook | No | A Restaurant Bill Splitter workbook to copy. If absent, build the sheet from `references/template-layout.md`. |

Never invent an amount, a name, a date or a tip. If a figure cannot be read,
ask for it.

## Outcome

1. A **new** workbook file in the user's output location containing a sheet
   named for the meal within Excel's naming limits, laid out as `references/template-layout.md`
   describes, with the receipt lines, the share entries, the live formulas and
   the WHO OWES WHAT block filled in. Never modify a supplied template
   workbook in place — copy it and leave its own sheets untouched.
2. A short chat summary: one line per person with the amount owed, the bill
   total, and confirmation that the check reconciles to zero.

Both are local writes. This workflow performs no business writes, sends
nothing, and needs no connection.

## Method

### Step 1 — Read the receipt

Read the supplied receipt file. Extract, and only from what is actually
legible:

- restaurant name and date (for the default meal label and filename);
- every printed line: its text, its printed quantity if shown, its amount;
- the items subtotal, the tax amount, and the gratuity amount and rate if the
  receipt prints one.

Check that the line amounts add to the printed subtotal before going on. If
they do not, or a line is unreadable, stop and ask for the missing figures.
Do not estimate, and do not adjust an amount so the totals agree.

### Step 2 — Agree who had what

Never assume silently. If the user has not already said who had what, ask
before calculating — list the lines and ask who had each, or ask them to
confirm an even split.

- If the user answers, use their answer.
- If the user explicitly declines to specify assignments, disclose the
  **even split** fallback: one share for every named diner on every line.
  Say in the summary that this was assumed. An unanswered question is not a
  decline; wait for the answer rather than treating silence as agreement.

Convert the agreement into whole-number shares per line per person:

- A share is a portion of a line, not a physical item. One cake split three
  ways is 3 shares of 1, so each pays a third.
- Someone who had more takes more shares. A line printed as "4 CRAFT BEER
  28.00" where one person had two is 4 shares at 7.00, with 2 against that
  person.
- A multi-quantity line follows the printed quantity when the diners between
  them had all of it; a single-quantity shared plate gets one share per diner
  who had it.
- Someone who did not have a line takes no share of it.

Every line must end with at least one share against it. Stop and ask rather
than guessing on a line nobody claims. The sheet holds 20 lines and 8 diners;
if the receipt or party is larger, say so and ask how to proceed rather than
truncating.

### Step 3 — Compute the split

Do not do this arithmetic by hand. Build a meal JSON file and run the bundled
helper, which rounds to whole cents and reconciles the remainder. Locate this
skill's own `scripts/split_bill.py` and its sibling `safe_json.py` through the
native resource listing. Invoke that actual script with the existing Python
interpreter and `--input` and `--output`, each followed by the actual meal JSON
path and a new result JSON path as separate arguments. Do not use development
checkout paths or a copy of the Creator's helper.

The input contract, the rounding rule and every rejection message are
documented in `references/helper-contract.md`. Read it before building the
JSON. The helper exits non-zero with a specific message and writes nothing on
any validation failure — relay that message to the user rather than working
around it.

Always supply `printed_subtotal` after reading the receipt. Supply
`printed_total` only for the total that includes the tax and selected gratuity;
do not compare a pre-tip total to a tip-inclusive result. If the user changes
a tip already printed on a paid receipt, ask whether to split the actual
payment or calculate a hypothetical new total.

### Step 4 — Build the workbook

Copy the supplied template workbook if there is one, otherwise create a new
workbook, and add one sheet named for the meal label. Fill it in exactly as
`references/template-layout.md` specifies: the bill totals block, the itemized
lines and share entries, and the per-person block, keeping the template's
formulas so the sheet recalculates if the user edits it. Follow the reference's
explicit printed-gratuity override rather than recomputing an amount from a
rounded percentage. Write the helper's reconciled figures alongside the
formulas as the amounts to pay, clearly labeled as a snapshot. Re-run the helper
to refresh those figures after edits; they are not live formulas.

Save to the requested output filename in the user's output location. If a file
with that name already exists, ask for a different destination; do not
overwrite it. If the workbook cannot be written, say so and provide the summary
plus the computed figures instead of claiming a file exists.

### Step 5 — Verify, then report

Before presenting anything as final, confirm:

- the entered line amounts equal the receipt's printed subtotal;
- every line carries at least one share;
- the per-person totals sum exactly to the grand total (check = 0.00);
- the grand total equals the receipt's total paid, when supplied with the same
  tip basis (otherwise label it as a calculated total, not a verified payment).

If any check fails, name the line or figure at fault instead of presenting
totals. Otherwise report each person's total owed, the bill total, the tip
basis used (receipt gratuity, user's rate, or the 18% fallback), and whether
shares came from the user or from the even-split assumption.

## What to say when something is missing

| Situation | Response |
|---|---|
| Receipt unreadable or cropped | Ask for a clearer image or the missing line amounts. Do not estimate. |
| Lines do not match the printed subtotal | Report the difference and the suspect lines; do not adjust. |
| A line nobody claims | Name the line and ask who had it. |
| A name in the assignment is not a diner | Ask the user to reconcile the names. |
| More than 8 diners or 20 lines | Explain the sheet's limits and ask how to proceed. |
| No spreadsheet editing available | Give the full per-person figures in chat and say the workbook could not be created. |

## Invoking it again

The process is manual and configurable; nothing here is tied to one meal:

- "Split this receipt between Ana, Bo and Cleo — Cleo had the steak, the rest
  we shared. Call it Harbour Grill and save it as harbour-grill-split.xlsx."
- "Here's last night's bill for four. Even split, 15% tip."
- "Split this among six of us using my Restaurant Bill Splitter workbook."

This skill needs only the new receipt, diner choices and output locations.
The original recording, example receipts, workbook and Creator are not runtime
dependencies. Native installation, independent invocation and workbook creation
for this contributed revision remain unverified; scheduling is not provided.
