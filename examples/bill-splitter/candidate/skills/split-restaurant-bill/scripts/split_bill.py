"""Deterministic restaurant bill split.

Reads one bounded JSON file describing a meal (diners, receipt lines, the
shares each diner takes of each line, tax and tip) and writes one new JSON
file with the per-person amounts owed, rounded to whole cents and
reconciled so the per-person totals sum exactly to the grand total.

Standard library only. No network, no external tools, no state.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from math import lcm
from pathlib import Path

from safe_json import InputError, load_json, write_new_text

MAX_DINERS = 8
MAX_LINES = 20
MAX_SHARES_PER_CELL = 99
MAX_LABEL = 120
MAX_MONEY_CENTS = 99_999_999_999
MAX_RATE_PLACES = 6

ROOT_KEYS = {
    "meal_label",
    "diners",
    "lines",
    "tax",
    "tip_rate",
    "tip_amount",
    "printed_subtotal",
    "printed_total",
}
LINE_KEYS = {"label", "amount", "shares"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def _decimal(value: object, label: str) -> Decimal:
    _require(type(value) is not bool, f"{label}: expected a number, not a boolean.")
    _require(isinstance(value, (int, float, Decimal)), f"{label}: expected a number.")
    amount = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    _require(amount.is_finite(), f"{label}: must be a finite number.")
    return amount


def _money(value: object, label: str, *, allow_zero: bool = True,
           maximum: int = MAX_MONEY_CENTS) -> int:
    """Validate exact decimal input, then use integer cents for all arithmetic."""
    amount = _decimal(value, label)
    _require(amount >= 0, f"{label}: must not be negative.")
    _require(allow_zero or amount > 0, f"{label}: must be greater than zero.")
    _require(amount <= Decimal(_format_cents(maximum)), f"{label}: must be at most {_format_cents(maximum)}.")
    _require(-amount.as_tuple().exponent <= 2, f"{label}: at most 2 decimal places are supported.")
    numerator, denominator = amount.as_integer_ratio()
    return numerator * 100 // denominator


def _rate(value: object, label: str) -> Decimal:
    rate = _decimal(value, label)
    _require(0 <= rate <= 1, f"{label}: use a fraction between 0 and 1, e.g. 0.2 for 20 percent.")
    _require(-rate.as_tuple().exponent <= MAX_RATE_PLACES,
             f"{label}: at most {MAX_RATE_PLACES} decimal places are supported.")
    return rate


def _text(value: object, label: str, limit: int) -> str:
    _require(isinstance(value, str), f"{label}: expected text.")
    cleaned = value.strip()
    _require(cleaned != "", f"{label}: must not be empty.")
    _require(len(cleaned) <= limit, f"{label}: must be at most {limit} characters.")
    return cleaned


def _shares(value: object, diners: list, label: str) -> dict:
    _require(isinstance(value, dict), f"{label}: expected an object of name to share count.")
    known = set(diners)
    result = {name: 0 for name in diners}
    for name, count in value.items():
        _require(name in known, f"{label}: '{name}' is not one of the named diners.")
        _require(type(count) is not bool, f"{label}.{name}: expected a whole number, not a boolean.")
        _require(isinstance(count, int), f"{label}.{name}: expected a whole number of shares.")
        _require(0 <= count <= MAX_SHARES_PER_CELL, f"{label}.{name}: shares must be 0-{MAX_SHARES_PER_CELL}.")
        result[name] = count
    return result


def _format_cents(value: int) -> str:
    sign = "-" if value < 0 else ""
    whole, cents = divmod(abs(value), 100)
    return f"{sign}{whole}.{cents:02d}"


def _round_ratio(numerator: int, denominator: int) -> int:
    whole, remainder = divmod(numerator, denominator)
    return whole + (2 * remainder >= denominator)


def _allocate(weights: list[int], total: int) -> list[int]:
    """Largest remainders in integer cents; exact ties follow diner order."""
    denominator = sum(weights)
    _require(denominator > 0, "Rounding: there are no positive shares to allocate.")
    portions = [divmod(weight * total, denominator) for weight in weights]
    result = [whole for whole, _ in portions]
    cents_left = total - sum(result)
    _require(0 <= cents_left < len(weights), "Rounding: the remainder is outside the diner bound.")
    order = sorted(range(len(weights)), key=lambda index: (-portions[index][1], index))
    for index in order[:cents_left]:
        result[index] += 1
    return result


def compute(meal: object) -> dict:
    _require(isinstance(meal, dict), "Input: the top level must be a JSON object.")
    unknown = sorted(set(meal) - ROOT_KEYS)
    _require(not unknown, f"Input: unsupported field(s) {', '.join(unknown)}.")
    for required in ("diners", "lines", "tax"):
        _require(required in meal, f"Input: '{required}' is required.")

    raw_diners = meal["diners"]
    _require(isinstance(raw_diners, list), "diners: expected a list of names.")
    _require(1 <= len(raw_diners) <= MAX_DINERS, f"diners: supply 1-{MAX_DINERS} names; the sheet has {MAX_DINERS} person columns.")
    diners = [_text(name, f"diners[{index}]", 64) for index, name in enumerate(raw_diners)]
    _require(len(set(diners)) == len(diners), "diners: names must be unique so each column is unambiguous.")

    raw_lines = meal["lines"]
    _require(isinstance(raw_lines, list), "lines: expected a list of receipt lines.")
    _require(1 <= len(raw_lines) <= MAX_LINES, f"lines: supply 1-{MAX_LINES} lines; the itemized block holds {MAX_LINES} rows.")

    lines = []
    subtotal = 0
    for index, raw in enumerate(raw_lines):
        where = f"lines[{index}]"
        _require(isinstance(raw, dict), f"{where}: expected an object.")
        missing = sorted(LINE_KEYS - set(raw))
        _require(not missing, f"{where}: missing {', '.join(missing)}.")
        extra = sorted(set(raw) - LINE_KEYS)
        _require(not extra, f"{where}: unsupported field(s) {', '.join(extra)}.")
        label = _text(raw["label"], f"{where}.label", MAX_LABEL)
        amount = _money(raw["amount"], f"{where}.amount", allow_zero=False)
        shares = _shares(raw["shares"], diners, f"{where}.shares")
        claimed = sum(shares.values())
        _require(
            claimed > 0,
            f"{where}: '{label}' has no shares against it. Every line needs at least one share, or the check row will not be zero.",
        )
        lines.append(
            {
                "label": label,
                "amount": amount,
                "shares_claimed": claimed,
                "shares": shares,
            }
        )
        subtotal += amount

    if "printed_subtotal" in meal:
        printed = _money(meal["printed_subtotal"], "printed_subtotal", maximum=MAX_LINES * MAX_MONEY_CENTS)
        _require(
            printed == subtotal,
            f"printed_subtotal: the entered lines total {_format_cents(subtotal)} but the receipt prints {_format_cents(printed)} "
            f"(difference {_format_cents(subtotal - printed)}). Fix the lines rather than adjusting a figure.",
        )

    tax = _money(meal["tax"], "tax")

    has_rate = "tip_rate" in meal
    has_amount = "tip_amount" in meal
    _require(has_rate or has_amount, "tip: supply either 'tip_amount' (the gratuity printed on the receipt) or 'tip_rate'.")
    _require(not (has_rate and has_amount), "tip: supply only one of 'tip_amount' or 'tip_rate'.")
    if has_amount:
        tip = _money(meal["tip_amount"], "tip_amount")
        rate_numerator, rate_denominator = tip, subtotal
    else:
        tip_rate = _rate(meal["tip_rate"], "tip_rate")
        rate_numerator, rate_denominator = tip_rate.as_integer_ratio()
        tip = _round_ratio(subtotal * rate_numerator, rate_denominator)

    grand_total = subtotal + tax + tip
    if "printed_total" in meal:
        printed_total = _money(meal["printed_total"], "printed_total",
                               maximum=(2 * MAX_LINES + 1) * MAX_MONEY_CENTS)
        _require(
            printed_total == grand_total,
            f"printed_total: the computed grand total is {_format_cents(grand_total)} but the receipt prints {_format_cents(printed_total)} "
            f"(difference {_format_cents(grand_total - printed_total)}). Check the tax and tip figures.",
        )

    # A common denominator preserves exact fractional shares without decimal
    # division or accumulation-order errors. There are at most 20 divisors <=792.
    denominator = lcm(*(line["shares_claimed"] for line in lines))
    weights = [
        sum(line["amount"] * (denominator // line["shares_claimed"]) * line["shares"][name]
            for line in lines)
        for name in diners
    ]
    items_cents = _allocate(weights, subtotal)
    tax_cents = _allocate(weights, tax)
    tip_cents = _allocate(weights, tip)

    people = []
    for index, name in enumerate(diners):
        total_owed = items_cents[index] + tax_cents[index] + tip_cents[index]
        people.append(
            {
                "name": name,
                "items": _format_cents(items_cents[index]),
                "tax_share": _format_cents(tax_cents[index]),
                "tip_share": _format_cents(tip_cents[index]),
                "total_owed": _format_cents(total_owed),
            }
        )

    collected = sum(items_cents) + sum(tax_cents) + sum(tip_cents)
    check = collected - grand_total
    _require(
        check == 0,
        f"Reconciliation: the per-person totals sum to {_format_cents(collected)} but the grand total is {_format_cents(grand_total)}.",
    )

    meal_label = _text(meal["meal_label"], "meal_label", 64) if "meal_label" in meal else None

    return {
        "meal_label": meal_label,
        "items_subtotal": _format_cents(subtotal),
        "tax": _format_cents(tax),
        "tip_rate": _format_cents(_round_ratio(rate_numerator * 10000, rate_denominator)),
        "tip": _format_cents(tip),
        "grand_total": _format_cents(grand_total),
        "check": "0.00",
        "lines": [
            {
                "label": line["label"],
                "amount": _format_cents(line["amount"]),
                "shares_claimed": line["shares_claimed"],
                "cost_per_share": _format_cents(_round_ratio(line["amount"], line["shares_claimed"])),
                "shares": {name: count for name, count in line["shares"].items() if count},
            }
            for line in lines
        ],
        "people": people,
    }


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split an itemized restaurant bill by shares.")
    parser.add_argument("--input", required=True, help="Path to the meal JSON file to read.")
    parser.add_argument("--output", required=True, help="Path of the new JSON file to create.")
    args = parser.parse_args(argv)

    try:
        meal = load_json(Path(args.input), max_bytes=200_000, max_depth=8)
        result = compute(meal)
        payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        write_new_text(Path(args.output), payload)
    except InputError as exc:
        print(f"bill-split error: {exc}", file=sys.stderr)
        return 2
    except FileExistsError:
        print(f"bill-split error: output file already exists: {args.output}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"bill-split error: file system error ({exc.strerror}): {exc.filename!r}.", file=sys.stderr)
        return 2
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
