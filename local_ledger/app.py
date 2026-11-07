"""CustomTkinter user interface for Local Ledger."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .csv_service import export_monthly_report, import_transactions
from .database import Database
from .validation import (
    ValidationError,
    format_pounds,
    parse_amount_to_cents,
    parse_transaction_date,
    require_text,
    validate_kind,
    validate_month,
)


APP_NAME = "Local Ledger"
COLOURS = {"navy": "#14213D", "blue": "#2F80ED", "green": "#27AE60", "red": "#EB5757", "muted": "#6B7280"}


class LocalLedgerApp(ctk.CTk):
    def __init__(self, database: Database):
        super().__init__()
        self.database = database
        self.title(APP_NAME)
        self.geometry("1180x760")
        self.minsize(980, 650)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.current_month = tk.StringVar(value=date.today().strftime("%Y-%m"))
        self.category_lookup: dict[str, int] = {}
        self._build_layout()
        self.refresh_all()

    def _build_layout(self) -> None:
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=COLOURS["navy"], height=76)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="LOCAL LEDGER", font=ctk.CTkFont(size=24, weight="bold"), text_color="white").pack(side="left", padx=28)
        ctk.CTkLabel(header, text="Income • expenses • monthly budgets", text_color="#CBD5E1").pack(side="left")

        self.tabs = ctk.CTkTabview(self, segmented_button_selected_color=COLOURS["blue"])
        self.tabs.pack(fill="both", expand=True, padx=20, pady=16)
        for name in ("Dashboard", "Transactions", "Budgets", "Import & Export"):
            self.tabs.add(name)

        self._build_dashboard(self.tabs.tab("Dashboard"))
        self._build_transactions(self.tabs.tab("Transactions"))
        self._build_budgets(self.tabs.tab("Budgets"))
        self._build_import_export(self.tabs.tab("Import & Export"))

    def _month_controls(self, parent: ctk.CTkFrame, command) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(frame, text="Month (YYYY-MM)").pack(side="left", padx=(0, 8))
        ctk.CTkEntry(frame, textvariable=self.current_month, width=120).pack(side="left")
        ctk.CTkButton(frame, text="Refresh", width=90, command=command).pack(side="left", padx=8)
        return frame

    def _build_dashboard(self, tab: ctk.CTkFrame) -> None:
        self._month_controls(tab, self.refresh_all).pack(fill="x", pady=(8, 16))
        cards = ctk.CTkFrame(tab, fg_color="transparent")
        cards.pack(fill="x")
        self.summary_labels: dict[str, ctk.CTkLabel] = {}
        for title, key, colour in (("Income", "income", COLOURS["green"]), ("Expenses", "expenses", COLOURS["red"]), ("Balance", "balance", COLOURS["blue"])):
            card = ctk.CTkFrame(cards)
            card.pack(side="left", fill="x", expand=True, padx=6)
            ctk.CTkLabel(card, text=title, text_color=COLOURS["muted"], font=ctk.CTkFont(size=14)).pack(pady=(18, 2))
            label = ctk.CTkLabel(card, text="£0.00", text_color=colour, font=ctk.CTkFont(size=28, weight="bold"))
            label.pack(pady=(0, 18))
            self.summary_labels[key] = label

        content = ctk.CTkFrame(tab, fg_color="transparent")
        content.pack(fill="both", expand=True, pady=18)
        chart_frame = ctk.CTkFrame(content)
        chart_frame.pack(side="left", fill="both", expand=True, padx=(6, 8))
        ctk.CTkLabel(chart_frame, text="Spending by category", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=18, pady=(16, 4))
        self.chart = tk.Canvas(chart_frame, bg="#F8FAFC", highlightthickness=0, height=330)
        self.chart.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        self.chart.bind("<Configure>", lambda _event: self.refresh_dashboard())

        budget_frame = ctk.CTkFrame(content, width=390)
        budget_frame.pack(side="left", fill="both", padx=(8, 6))
        budget_frame.pack_propagate(False)
        ctk.CTkLabel(budget_frame, text="Budget progress", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=18, pady=(16, 8))
        self.budget_progress = ctk.CTkScrollableFrame(budget_frame, fg_color="transparent")
        self.budget_progress.pack(fill="both", expand=True, padx=8, pady=(0, 12))

    def _build_transactions(self, tab: ctk.CTkFrame) -> None:
        form = ctk.CTkFrame(tab)
        form.pack(fill="x", pady=(8, 12))
        fields = ctk.CTkFrame(form, fg_color="transparent")
        fields.pack(fill="x", padx=16, pady=14)
        self.txn_date = ctk.CTkEntry(fields, placeholder_text="YYYY-MM-DD", width=130)
        self.txn_date.insert(0, date.today().isoformat())
        self.txn_description = ctk.CTkEntry(fields, placeholder_text="Description", width=230)
        self.txn_amount = ctk.CTkEntry(fields, placeholder_text="Amount", width=120)
        self.txn_kind = ctk.CTkOptionMenu(fields, values=["expense", "income"], command=lambda _v: self._refresh_category_menu())
        self.txn_category = ctk.CTkOptionMenu(fields, values=["Loading..."])
        for widget in (self.txn_date, self.txn_description, self.txn_amount, self.txn_kind, self.txn_category):
            widget.pack(side="left", padx=5)
        ctk.CTkButton(fields, text="Add transaction", command=self.add_transaction).pack(side="left", padx=8)

        controls = ctk.CTkFrame(tab, fg_color="transparent")
        controls.pack(fill="x")
        self._month_controls(controls, self.refresh_transactions).pack(side="left")
        ctk.CTkButton(controls, text="Delete selected", fg_color=COLOURS["red"], hover_color="#C0392B", command=self.delete_selected_transaction).pack(side="right")

        columns = ("date", "description", "category", "type", "amount")
        self.transaction_tree = ttk.Treeview(tab, columns=columns, show="headings", selectmode="browse")
        headings = {"date": "Date", "description": "Description", "category": "Category", "type": "Type", "amount": "Amount"}
        widths = {"date": 110, "description": 320, "category": 180, "type": 100, "amount": 130}
        for column in columns:
            self.transaction_tree.heading(column, text=headings[column])
            self.transaction_tree.column(column, width=widths[column], anchor="e" if column == "amount" else "w")
        self.transaction_tree.pack(fill="both", expand=True, pady=(10, 4))

    def _build_budgets(self, tab: ctk.CTkFrame) -> None:
        form = ctk.CTkFrame(tab)
        form.pack(fill="x", pady=(8, 14))
        self._month_controls(form, self.refresh_budgets).pack(side="left", padx=14, pady=14)
        self.budget_category = ctk.CTkOptionMenu(form, values=["Loading..."], width=190)
        self.budget_category.pack(side="left", padx=6)
        self.budget_amount = ctk.CTkEntry(form, placeholder_text="Monthly limit", width=140)
        self.budget_amount.pack(side="left", padx=6)
        ctk.CTkButton(form, text="Set budget", command=self.set_budget).pack(side="left", padx=8)

        columns = ("category", "limit", "spent", "remaining", "status")
        self.budget_tree = ttk.Treeview(tab, columns=columns, show="headings")
        for column, label, width in (("category", "Category", 240), ("limit", "Budget", 150), ("spent", "Spent", 150), ("remaining", "Remaining", 150), ("status", "Status", 160)):
            self.budget_tree.heading(column, text=label)
            self.budget_tree.column(column, width=width, anchor="e" if column in {"limit", "spent", "remaining"} else "w")
        self.budget_tree.pack(fill="both", expand=True)

    def _build_import_export(self, tab: ctk.CTkFrame) -> None:
        intro = ctk.CTkFrame(tab)
        intro.pack(fill="x", pady=(8, 16))
        ctk.CTkLabel(intro, text="Move data with CSV files", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(intro, text="Required import columns: date, description and amount. Optional columns: category, type and notes. Negative amounts are treated as expenses when type is absent.", wraplength=900, justify="left").pack(anchor="w", padx=20, pady=(0, 18))

        actions = ctk.CTkFrame(tab, fg_color="transparent")
        actions.pack(fill="x")
        ctk.CTkButton(actions, text="Import bank CSV", height=44, command=self.import_csv).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="Export monthly report", height=44, command=self.export_csv).pack(side="left", padx=10)
        self._month_controls(actions, self.refresh_all).pack(side="right")

        self.import_log = ctk.CTkTextbox(tab, height=360)
        self.import_log.pack(fill="both", expand=True, pady=18)
        self.import_log.insert("1.0", "Import results will appear here. Invalid rows are skipped and listed with their CSV line number.\n")
        self.import_log.configure(state="disabled")

    def _validated_month(self) -> str:
        return validate_month(self.current_month.get())

    def _refresh_category_menu(self) -> None:
        kind = validate_kind(self.txn_kind.get())
        rows = self.database.list_categories(kind)
        values = [row["name"] for row in rows]
        self.category_lookup.update({row["name"]: int(row["id"]) for row in rows})
        self.txn_category.configure(values=values)
        if values:
            self.txn_category.set(values[0])

    def refresh_all(self) -> None:
        try:
            self._validated_month()
            self._refresh_category_menu()
            expense_rows = self.database.list_categories("expense")
            expense_names = [row["name"] for row in expense_rows]
            self.category_lookup.update({row["name"]: int(row["id"]) for row in expense_rows})
            self.budget_category.configure(values=expense_names)
            if expense_names and self.budget_category.get() not in expense_names:
                self.budget_category.set(expense_names[0])
            self.refresh_dashboard()
            self.refresh_transactions()
            self.refresh_budgets()
        except ValidationError as exc:
            messagebox.showerror("Invalid month", str(exc))

    def refresh_dashboard(self) -> None:
        try:
            month = self._validated_month()
        except ValidationError:
            return
        summary = self.database.monthly_summary(month)
        for key, value in summary.items():
            self.summary_labels[key].configure(text=format_pounds(value))
        self._draw_chart(self.database.spending_by_category(month))
        for child in self.budget_progress.winfo_children():
            child.destroy()
        rows = self.database.budget_status(month)
        if not rows:
            ctk.CTkLabel(self.budget_progress, text="No budgets set for this month.", text_color=COLOURS["muted"]).pack(pady=24)
        for row in rows:
            limit = int(row["limit_cents"])
            spent = int(row["spent_cents"])
            label = ctk.CTkLabel(self.budget_progress, text=f"{row['category_name']}  {format_pounds(spent)} / {format_pounds(limit)}")
            label.pack(anchor="w", padx=8, pady=(8, 2))
            bar = ctk.CTkProgressBar(self.budget_progress, progress_color=COLOURS["red"] if spent > limit else COLOURS["green"])
            bar.pack(fill="x", padx=8)
            bar.set(min(spent / limit, 1.0))

    def _draw_chart(self, rows) -> None:
        self.chart.delete("all")
        width = max(self.chart.winfo_width(), 500)
        rows = list(rows)[:7]
        if not rows:
            self.chart.create_text(width / 2, 150, text="Add expenses to see your spending pattern", fill=COLOURS["muted"], font=("Segoe UI", 12))
            return
        maximum = max(int(row["spent_cents"]) for row in rows)
        for index, row in enumerate(rows):
            y = 28 + index * 42
            value = int(row["spent_cents"])
            bar_width = (width - 245) * value / maximum
            self.chart.create_text(12, y + 10, text=str(row["category_name"])[:18], anchor="w", fill="#1F2937", font=("Segoe UI", 10))
            self.chart.create_rectangle(145, y, 145 + bar_width, y + 22, fill=COLOURS["blue"], outline="")
            self.chart.create_text(width - 12, y + 10, text=format_pounds(value), anchor="e", fill="#1F2937", font=("Segoe UI", 10, "bold"))

    def refresh_transactions(self) -> None:
        try:
            month = self._validated_month()
        except ValidationError:
            return
        for item in self.transaction_tree.get_children():
            self.transaction_tree.delete(item)
        for row in self.database.list_transactions(month):
            self.transaction_tree.insert("", "end", iid=str(row["id"]), values=(row["transaction_date"], row["description"], row["category_name"], row["kind"].title(), format_pounds(int(row["amount_cents"]))))

    def refresh_budgets(self) -> None:
        try:
            month = self._validated_month()
        except ValidationError:
            return
        for item in self.budget_tree.get_children():
            self.budget_tree.delete(item)
        for row in self.database.budget_status(month):
            limit = int(row["limit_cents"])
            spent = int(row["spent_cents"])
            remaining = limit - spent
            status = "Over budget" if remaining < 0 else "On track"
            self.budget_tree.insert("", "end", values=(row["category_name"], format_pounds(limit), format_pounds(spent), format_pounds(remaining), status))

    def add_transaction(self) -> None:
        try:
            transaction_date = parse_transaction_date(self.txn_date.get())
            description = require_text(self.txn_description.get(), "Description")
            amount_cents = parse_amount_to_cents(self.txn_amount.get())
            category_id = self.category_lookup[self.txn_category.get()]
            self.database.add_transaction(transaction_date, description, amount_cents, category_id)
            self.txn_description.delete(0, "end")
            self.txn_amount.delete(0, "end")
            self.current_month.set(transaction_date[:7])
            self.refresh_all()
        except (ValidationError, KeyError, ValueError) as exc:
            messagebox.showerror("Transaction not added", str(exc))

    def delete_selected_transaction(self) -> None:
        selected = self.transaction_tree.selection()
        if not selected:
            messagebox.showinfo("Select a transaction", "Choose a transaction in the table first.")
            return
        if messagebox.askyesno("Delete transaction", "Delete the selected transaction?"):
            self.database.delete_transaction(int(selected[0]))
            self.refresh_all()

    def set_budget(self) -> None:
        try:
            month = self._validated_month()
            limit_cents = parse_amount_to_cents(self.budget_amount.get())
            category_id = self.category_lookup[self.budget_category.get()]
            self.database.set_budget(category_id, month, limit_cents)
            self.budget_amount.delete(0, "end")
            self.refresh_all()
        except (ValidationError, KeyError, ValueError) as exc:
            messagebox.showerror("Budget not saved", str(exc))

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(title="Choose a bank CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            result = import_transactions(self.database, path)
            lines = [f"Imported: {result.imported}", f"Blank rows skipped: {result.skipped}", f"Rows with errors: {len(result.errors)}", ""]
            lines.extend(f"Line {error.line_number}: {error.message}" for error in result.errors)
            self.import_log.configure(state="normal")
            self.import_log.delete("1.0", "end")
            self.import_log.insert("1.0", "\n".join(lines))
            self.import_log.configure(state="disabled")
            self.refresh_all()
            messagebox.showinfo("Import complete", f"Imported {result.imported} transaction(s).")
        except (OSError, ValidationError, csv.Error) as exc:
            messagebox.showerror("Import failed", str(exc))

    def export_csv(self) -> None:
        try:
            month = self._validated_month()
            path = filedialog.asksaveasfilename(title="Save monthly report", defaultextension=".csv", initialfile=f"local-ledger-{month}.csv", filetypes=[("CSV files", "*.csv")])
            if not path:
                return
            export_monthly_report(self.database, month, path)
            messagebox.showinfo("Report exported", f"Saved report for {month}.")
        except (OSError, ValidationError) as exc:
            messagebox.showerror("Export failed", str(exc))


def default_database_path() -> Path:
    return Path.home() / "LocalLedgerData" / "local_ledger.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Local Ledger desktop application.")
    parser.add_argument("--database", type=Path, default=default_database_path(), help="SQLite database path")
    arguments = parser.parse_args()
    app = LocalLedgerApp(Database(arguments.database))
    app.mainloop()


if __name__ == "__main__":
    main()


