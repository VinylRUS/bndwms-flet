from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import flet as ft

APP_NAME = "BnDWMS"
STORAGE_DIR = Path.home() / ".bndwms"
STATE_PATH = STORAGE_DIR / "state.json"

COLORS = {
    "accent": "#ff8025",
    "bg": "#0f0f0f",
    "panel": "#111111",
    "surface": "#151515",
    "muted": "#b9b9b9",
    "border": "#252525",
}


@dataclass
class WMSState:
    db_url: str = ""
    users: dict[str, str] = field(default_factory=lambda: {"Admin": "Zhabus", "Оператор": "123456"})
    warehouses: list[str] = field(default_factory=lambda: ["Основной"])
    stock_rows: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"article": "A-100", "name": "Тестовый товар", "qty": "25"},
            {"article": "A-220", "name": "Кабель UTP", "qty": "13"},
            {"article": "B-007", "name": "Сканер", "qty": "4"},
        ]
    )

    @classmethod
    def load(cls) -> "WMSState":
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        if not STATE_PATH.exists():
            state = cls()
            state.save()
            return state

        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state = cls()
            state.db_url = str(raw.get("db_url", ""))
            state.users = dict(raw.get("users", state.users))
            state.warehouses = list(raw.get("warehouses", state.warehouses))
            rows = raw.get("stock_rows", state.stock_rows)
            state.stock_rows = [
                {
                    "article": str(item.get("article", "")),
                    "name": str(item.get("name", "")),
                    "qty": str(item.get("qty", "0")),
                }
                for item in rows
                if isinstance(item, dict)
            ] or state.stock_rows
            return state
        except Exception:
            fallback = cls()
            fallback.save()
            return fallback

    def save(self) -> None:
        payload = {
            "db_url": self.db_url,
            "users": self.users,
            "warehouses": self.warehouses,
            "stock_rows": self.stock_rows,
        }
        STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class BndWmsApplication:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.state = WMSState.load()
        self.active_user = ""
        self.status_line = ft.Text("Готово", color=COLORS["muted"], size=12)

        self.tabs = ft.Tabs(
            tabs=[],
            selected_index=0,
            indicator_color=COLORS["accent"],
            divider_color=COLORS["border"],
            label_color=ft.Colors.WHITE,
            unselected_label_color=COLORS["muted"],
            animation_duration=180,
            expand=1,
        )

    def start(self) -> None:
        self.page.title = f"{APP_NAME} — Flet"
        self.page.bgcolor = COLORS["bg"]
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.theme = ft.Theme(color_scheme_seed=COLORS["accent"])
        self.page.padding = 18
        self.page.window.min_width = 980
        self.page.window.min_height = 640
        self.page.on_keyboard_event = self._on_hotkey

        self.page.controls.clear()
        self.page.add(self._login_screen())
        self.page.update()

    def _login_screen(self) -> ft.Control:
        fio = ft.TextField(label="ФИО", autofocus=True, bgcolor=COLORS["surface"], border_radius=10)
        pin = ft.TextField(
            label="PIN",
            password=True,
            can_reveal_password=True,
            bgcolor=COLORS["surface"],
            border_radius=10,
        )
        warning = ft.Text("", color=ft.Colors.RED_300)

        def sign_in(_: ft.ControlEvent) -> None:
            username = (fio.value or "").strip()
            password = (pin.value or "").strip()

            if not username or not password:
                warning.value = "Введите ФИО и PIN"
                self.page.update()
                return

            if self.state.users.get(username) != password:
                warning.value = "Неверный логин или PIN"
                self.page.update()
                return

            self.active_user = username
            self.page.controls.clear()
            self.page.add(self._main_screen())
            self._set_status(f"Вход выполнен: {username}")

        return ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Container(
                width=390,
                padding=24,
                bgcolor=COLORS["panel"],
                border_radius=16,
                border=ft.border.all(1, COLORS["border"]),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text("Вход в BnDWMS", size=22, weight=ft.FontWeight.W_600),
                        ft.Text("Новый интерфейс на Flet", size=12, color=COLORS["muted"]),
                        fio,
                        pin,
                        warning,
                        ft.FilledButton("Войти", style=ft.ButtonStyle(bgcolor=COLORS["accent"]), on_click=sign_in),
                    ],
                ),
            ),
        )

    def _main_screen(self) -> ft.Control:
        self.tabs.tabs = [
            self._operation_tab("Приёмка"),
            self._operation_tab("Перемещение"),
            self._operation_tab("Списание"),
            self._operation_tab("Инвентаризация"),
            self._stock_tab(),
            self._settings_tab(),
        ]

        return ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(APP_NAME, size=24, weight=ft.FontWeight.W_700),
                                ft.Text(f"Пользователь: {self.active_user}", color=COLORS["muted"], size=12),
                            ],
                        ),
                        ft.Text("F1–F6 — быстрые вкладки", color=COLORS["muted"], size=11),
                    ],
                ),
                ft.Container(height=8),
                ft.Container(
                    expand=True,
                    padding=12,
                    bgcolor=COLORS["panel"],
                    border_radius=14,
                    content=self.tabs,
                ),
                ft.Container(
                    padding=10,
                    bgcolor="#121212",
                    border_radius=10,
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=COLORS["muted"]),
                        self.status_line,
                    ]),
                ),
            ],
        )

    def _operation_tab(self, title: str) -> ft.Tab:
        article = ft.TextField(label="Артикул", bgcolor=COLORS["surface"])
        qty = ft.TextField(label="Количество", bgcolor=COLORS["surface"])
        warehouse = ft.Dropdown(
            label="Склад",
            bgcolor=COLORS["surface"],
            value=self.state.warehouses[0] if self.state.warehouses else None,
            options=[ft.dropdown.Option(item) for item in self.state.warehouses],
        )

        def post_operation(_: ft.ControlEvent) -> None:
            self._set_status(
                f"{title}: артикул {article.value or '-'} / количество {qty.value or '-'} / склад {warehouse.value or '-'}"
            )

        return ft.Tab(
            text=title,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text(title, size=20, weight=ft.FontWeight.W_600),
                        ft.Text("Операция складского учёта.", color=COLORS["muted"]),
                        ft.Row([article, qty, warehouse]),
                        ft.FilledButton(
                            "Провести",
                            style=ft.ButtonStyle(bgcolor=COLORS["accent"]),
                            on_click=post_operation,
                        ),
                    ]
                ),
            ),
        )

    def _stock_tab(self) -> ft.Tab:
        table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Артикул")),
                ft.DataColumn(ft.Text("Название")),
                ft.DataColumn(ft.Text("Кол-во")),
            ],
            rows=[
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(row["article"])),
                        ft.DataCell(ft.Text(row["name"])),
                        ft.DataCell(ft.Text(row["qty"])),
                    ]
                )
                for row in self.state.stock_rows
            ],
        )

        return ft.Tab(
            text="Остатки",
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text("Остатки", size=20, weight=ft.FontWeight.W_600),
                        ft.Text("Снимок складских остатков из локального состояния.", color=COLORS["muted"]),
                        ft.Container(padding=12, bgcolor=COLORS["surface"], border_radius=12, content=table),
                    ]
                ),
            ),
        )

    def _settings_tab(self) -> ft.Tab:
        db_field = ft.TextField(label="PostgreSQL URL", value=self.state.db_url, bgcolor=COLORS["surface"])

        def persist(_: ft.ControlEvent) -> None:
            self.state.db_url = db_field.value or ""
            self.state.save()
            self._set_status("Настройки сохранены")

        return ft.Tab(
            text="Настройки",
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text("Настройки", size=20, weight=ft.FontWeight.W_600),
                        db_field,
                        ft.FilledButton(
                            "Сохранить",
                            style=ft.ButtonStyle(bgcolor=COLORS["accent"]),
                            on_click=persist,
                        ),
                    ]
                ),
            ),
        )

    def _set_status(self, message: str) -> None:
        self.status_line.value = message
        self.page.update()

    def _on_hotkey(self, event: ft.KeyboardEvent) -> None:
        mapping = {"F1": 0, "F2": 1, "F3": 2, "F4": 3, "F5": 4, "F6": 5}
        target = mapping.get(event.key)
        if target is None:
            return

        if 0 <= target < len(self.tabs.tabs):
            self.tabs.selected_index = target
            self.page.update()


def main(page: ft.Page) -> None:
    BndWmsApplication(page).start()


if __name__ == "__main__":
    ft.app(target=main)
