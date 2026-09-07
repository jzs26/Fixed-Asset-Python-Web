import csv
from datetime import date, datetime
from io import StringIO

from flask import Blueprint, Response, abort, render_template, request

from database import SessionLocal
from models import Asset


depreciation_bp = Blueprint("depreciation", __name__)


def _get_asset(asset_id):
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            abort(404)
        return asset
    finally:
        db.close()

@depreciation_bp.route("/depreciation/all/<depreciation_type>")
def all_active_depreciation(depreciation_type):
    if depreciation_type.lower() not in {"tax", "book"}:
        abort(400)

    reports, years, selected_year, grand_total = _active_reports(
        depreciation_type,
        request.args.get("year", type=int),
    )
    return render_template(
        "all_depreciation_report.html",
        reports=reports,
        years=years,
        selected_year=selected_year,
        grand_total=grand_total,
        depreciation_type=depreciation_type.title(),
    )


def _active_reports(depreciation_type, selected_year=None):
    db = SessionLocal()
    try:
        assets = (
            db.query(Asset)
            .filter(Asset.status == "ACTIVE")
            .order_by(Asset.asset_code)
            .all()
        )

        schedules = [
            (asset, _build_schedule(asset, depreciation_type))
            for asset in assets
        ]
        years = sorted({
            item["year"]
            for _, schedule in schedules
            for item in schedule
        })
        if selected_year not in years:
            current_year = datetime.now().year
            selected_year = (
                current_year if current_year in years else (years[-1] if years else None)
            )

        grouped = {}
        for asset, schedule in schedules:
            selected_schedule = [
                item for item in schedule if item["year"] == selected_year
            ]
            if selected_schedule:
                row = _build_report_row(
                    asset, selected_schedule[0], depreciation_type, selected_year
                )
                grouped.setdefault(
                    asset.asset_classification or "Unclassified", []
                ).append(row)

        grouped_reports = {
            classification: {
                "rows": rows,
                "totals": _calculate_totals(rows),
            }
            for classification, rows in grouped.items()
        }
        grand_total = _calculate_totals([
            row
            for report in grouped_reports.values()
            for row in report["rows"]
        ])

        return grouped_reports, years, selected_year, grand_total
    finally:
        db.close()


def _build_report_row(asset, item, depreciation_type, selected_year=None):
    prefix = depreciation_type.lower()
    original_cost = round(float(getattr(asset, f"{prefix}_original_cost") or 0), 2)
    depreciation = round(float(item["depreciation"]), 2)
    closing_wdv = round(float(item["closing_wdv"]), 2)
    method = (getattr(asset, f"{prefix}_depreciation_type") or "").lower()
    prime_depreciation = depreciation if "prime" in method else 0
    diminishing_depreciation = (
        depreciation if "diminishing" in method else 0
    )
    return {
        "asset": asset,
        "asset_code": asset.asset_code,
        "description": asset.description,
        "original_cost": original_cost,
        "opening_wdv": item["opening_wdv"],
        "addition_date": (
            asset.purchase_date
            if asset.purchase_date and asset.purchase_date.year == selected_year
            else None
        ),
        "additions_cost": (
            original_cost
            if asset.purchase_date and asset.purchase_date.year == selected_year
            else 0
        ),
        "prime_depreciation": prime_depreciation,
        "diminishing_depreciation": diminishing_depreciation,
        "total_depreciation": round(
            (prime_depreciation or diminishing_depreciation) + closing_wdv,
            2,
        ),
        "closing_wdv": closing_wdv,
    }


def _calculate_totals(rows):
    fields = [
        "original_cost",
        "opening_wdv",
        "additions_cost",
        "total_depreciation",
        "prime_depreciation",
        "diminishing_depreciation",
        "closing_wdv",
    ]
    return {
        field: round(sum(row[field] for row in rows), 2)
        for field in fields
    }

def _build_schedule(asset, depreciation_type):
    prefix = depreciation_type.lower()
    original_cost = float(getattr(asset, f"{prefix}_original_cost") or 0)
    opening_wdv = float(getattr(asset, f"opening_{prefix}_wdv") or original_cost)
    method = getattr(asset, f"{prefix}_depreciation_type") or "Prime Cost"
    rate = float(getattr(asset, f"{prefix}_depreciation_rate") or 0) / 100
    start_date = getattr(asset, f"{prefix}_depreciation_date") or date.today()

    schedule = []
    current_wdv = max(opening_wdv, 0)
    year = start_date.year

    for period in range(1, 101):
        if current_wdv <= 0 or rate <= 0:
            break

        if method == "Diminishing Value":
            depreciation = current_wdv * rate
        else:
            depreciation = original_cost * rate

        depreciation = min(depreciation, current_wdv)
        closing_wdv = current_wdv - depreciation
        schedule.append({
            "period": period,
            "year": year,
            "opening_wdv": round(current_wdv, 2),
            "depreciation": round(depreciation, 2),
            "closing_wdv": round(closing_wdv, 2),
        })
        current_wdv = closing_wdv
        year += 1

    return schedule


def _report(asset_id, depreciation_type):
    asset = _get_asset(asset_id)
    schedule = _build_schedule(asset, depreciation_type)
    return render_template(
        "depreciation_report.html",
        asset=asset,
        schedule=schedule,
        depreciation_type=depreciation_type,
    )


@depreciation_bp.route("/assets/<int:asset_id>/depreciation/tax")
def tax_depreciation(asset_id):
    return _report(asset_id, "Tax")


@depreciation_bp.route("/assets/<int:asset_id>/depreciation/book")
def book_depreciation(asset_id):
    return _report(asset_id, "Book")


@depreciation_bp.route(
    "/assets/<int:asset_id>/depreciation/<depreciation_type>/export/<file_format>"
)
def export_depreciation(asset_id, depreciation_type, file_format):
    if depreciation_type.lower() not in {"tax", "book"}:
        abort(400)
    if file_format.lower() not in {"csv", "text"}:
        abort(400)

    asset = _get_asset(asset_id)
    schedule = _build_schedule(asset, depreciation_type)
    headers = ["Period", "Year", "Opening WDV", "Depreciation", "Closing WDV"]
    rows = [
        [
            item["period"],
            item["year"],
            f"{item['opening_wdv']:.2f}",
            f"{item['depreciation']:.2f}",
            f"{item['closing_wdv']:.2f}",
        ]
        for item in schedule
    ]

    if file_format.lower() == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        content = output.getvalue()
        mimetype = "text/csv"
        extension = "csv"
    else:
        content = "\t".join(headers) + "\n"
        content += "\n".join("\t".join(map(str, row)) for row in rows) + "\n"
        mimetype = "text/plain"
        extension = "txt"

    filename = f"{asset.asset_code}_{depreciation_type.lower()}_depreciation.{extension}"
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@depreciation_bp.route(
    "/depreciation/all/<depreciation_type>/export/<file_format>"
)
def export_all_depreciation(depreciation_type, file_format):
    if depreciation_type.lower() not in {"tax", "book"}:
        abort(400)

    if file_format.lower() not in {"csv", "text"}:
        abort(400)

    selected_year = request.args.get("year", type=int)
    reports, _, selected_year, grand_total = _active_reports(
        depreciation_type, selected_year
    )
    headers = [
        "Asset Classification", "Asset Code", "Description", "Original Cost",
        "Opening WDV", "Addition Date", "Additions Cost",
        "Total Depreciation", "Prime Cost Depreciation",
        "Diminishing Value Depreciation", "Closing WDV",
    ]
    rows = []
    for classification, report in reports.items():
        for item in report["rows"]:
            rows.append(_export_row(classification, item))
        rows.append(_total_export_row(
            f"{classification} Total", report["totals"]
        ))
    rows.append(_total_export_row("Grand Total", grand_total))

    if file_format.lower() == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        content = output.getvalue()
        mimetype = "text/csv"
        extension = "csv"
    else:
        content = "\t".join(headers) + "\n"
        content += "\n".join(
            "\t".join(map(str, row)) for row in rows
        )
        content += "\n"
        mimetype = "text/plain"
        extension = "txt"

    filename = f"all_active_{depreciation_type.lower()}_depreciation.{extension}"
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _export_row(classification, row):
    return [
        classification, row["asset_code"], row["description"],
        f"{row['original_cost']:.2f}", f"{row['opening_wdv']:.2f}",
        row["addition_date"].strftime("%d/%m/%Y") if row["addition_date"] else "",
        f"{row['additions_cost']:.2f}" if row["additions_cost"] else "",
        f"{row['total_depreciation']:.2f}", f"{row['prime_depreciation']:.2f}",
        f"{row['diminishing_depreciation']:.2f}", f"{row['closing_wdv']:.2f}",
    ]


def _total_export_row(label, totals):
    return [
        label, "", "", f"{totals['original_cost']:.2f}",
        f"{totals['opening_wdv']:.2f}", "",
        f"{totals['additions_cost']:.2f}" if totals["additions_cost"] else "",
        f"{totals['total_depreciation']:.2f}",
        f"{totals['prime_depreciation']:.2f}",
        f"{totals['diminishing_depreciation']:.2f}",
        f"{totals['closing_wdv']:.2f}",
    ]
