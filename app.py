from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

import flet as ft

APP_DIR = Path.home() / ".bndwms"
STATE_FILE = APP_DIR / "state.json"

ACCENT = "#ff8025"
BG = "#0f0f0f"
SURFACE = "#151515"
TEXT_SECONDARY = "#b9b9b9"


@dataclass
class AppState:
    db_url: str = ""
    users: dict[str, str] | None = None
    warehouses: list[str] | None = None
    article_rows: list[tuple[str, str, str]] | None = None

    @staticmethod
    def defaults() -> "AppState":
        return AppState(
            db_url="",
            users={"Admin": "Zhabus", "Оператор": "123456"},
            warehouses=["Основной"],
            article_rows=[("A-100", "Тестовый товар", "25")],
        )


class Storage:
    def __init__(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppState:
        if not STATE_FILE.exists():
            state = AppState.defaults()
            self.save(state)
            return state

        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            defaults = AppState.defaults()
            return AppState(
                db_url=raw.get("db_url", ""),
                users=raw.get("users", defaults.users),
                warehouses=raw.get("warehouses", defaults.warehouses),
                article_rows=[tuple(x) for x in raw.get("article_rows", defaults.article_rows)],
            )
        except Exception:
            state = AppState.defaults()
            self.save(state)
            return state

    def save(self, state: AppState) -> None:
        payload = asdict(state)
        STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class WMSApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.storage = Storage()
        self.state = self.storage.load()
        self.current_user = ""

        self.status_text = ft.Text("Готово", color=TEXT_SECONDARY, size=12)
        self.tabs_ref = ft.Ref[ft.Tabs]()
        self.article_table = ft.DataTable(columns=[], rows=[])

    def run(self) -> None:
        self.page.title = "BnDWMS — Flet"
        self.page.bgcolor = BG
        self.page.padding = 18
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.theme = ft.Theme(color_scheme_seed=ACCENT, visual_density=ft.VisualDensity.COMPACT)
        self.page.window.min_width = 900
        self.page.window.min_height = 620
        self.page.on_keyboard_event = self.handle_keyboard
        self.page.add(self.build_login_view())

    def build_login_view(self) -> ft.Control:
        name_input = ft.TextField(label="ФИО", autofocus=True, bgcolor=SURFACE, border_radius=10)
        pin_input = ft.TextField(label="PIN", password=True, can_reveal_password=True, bgcolor=SURFACE, border_radius=10)
        error = ft.Text("", color=ft.Colors.RED_300)

        def do_login(_: ft.ControlEvent) -> None:
            name = (name_input.value or "").strip()
            pin = (pin_input.value or "").strip()

            if not name or not pin:
                error.value = "Введите ФИО и PIN"
                self.page.update()
                return

            if (self.state.users or {}).get(name) != pin:
                error.value = "Неверный логин или PIN"
                self.page.update()
                return

            self.current_user = name
            self.page.controls.clear()
            self.page.add(self.build_main_view())
            self.set_status(f"Вход выполнен: {name}")

        return ft.Container(
            expand=True,
            alignment=ft.Alignment(0, 0),
            content=ft.Container(
                width=380,
                bgcolor="#111111",
                padding=24,
                border_radius=16,
                border=ft.border.all(1, "#252525"),
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text("Вход в BnDWMS", size=22, weight=ft.FontWeight.W_600),
                        ft.Text("PyQt → Flet", size=12, color=TEXT_SECONDARY),
                        name_input,
                        pin_input,
                        error,
                        ft.FilledButton("Войти", on_click=do_login, style=ft.ButtonStyle(bgcolor=ACCENT)),
                    ],
                ),
            ),
        )

    def build_main_view(self) -> ft.Control:
        tabs = ft.Tabs(
            ref=self.tabs_ref,
            selected_index=0,
            animation_duration=150,
            divider_color="#252525",
            indicator_color=ACCENT,
            label_color=ft.Colors.WHITE,
            unselected_label_color=TEXT_SECONDARY,
            tabs=[
                self._tab("Приёмка"),
                self._tab("Перемещение"),
                self._tab("Списание"),
                self._tab("Инвентаризация"),
                self._stock_tab(),
                self._settings_tab(),
            ],
            expand=1,
        )

        header = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text("BnDWMS", size=24, weight=ft.FontWeight.W_700),
                        ft.Text(f"Пользователь: {self.current_user}", color=TEXT_SECONDARY, size=12),
                    ],
                ),
                ft.Text("F1/F2/F3/F4/F5 — быстрые вкладки", color=TEXT_SECONDARY, size=11),
            ],
        )

        return ft.Column(
            expand=True,
            controls=[
                header,
                ft.Container(height=8),
                ft.Container(expand=True, bgcolor="#111111", border_radius=14, padding=12, content=tabs),
                ft.Container(
                    bgcolor="#121212",
                    border_radius=10,
                    padding=10,
                    content=ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=TEXT_SECONDARY), self.status_text]),
                ),
            ],
        )

    def _tab(self, title: str) -> ft.Tab:
        return ft.Tab(
            text=title,
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text(title, size=20, weight=ft.FontWeight.W_600),
                        ft.Text("Логика перенесена с PyQt, UI обновлён под Flet.", color=TEXT_SECONDARY),
                        self._operation_form(title),
                    ]
                ),
            ),
        )

    def _operation_form(self, operation_name: str) -> ft.Control:
        article = ft.TextField(label="Артикул", bgcolor=SURFACE)
        qty = ft.TextField(label="Количество", bgcolor=SURFACE)
        warehouse = ft.Dropdown(
            label="Склад",
            bgcolor=SURFACE,
            options=[ft.dropdown.Option(x) for x in (self.state.warehouses or [])],
            value=(self.state.warehouses or [""])[0],
        )

        def submit(_: ft.ControlEvent) -> None:
            self.set_status(f"{operation_name}: артикул {article.value or '-'} / кол-во {qty.value or '-'}")

        return ft.Container(
            margin=ft.margin.only(top=8),
            content=ft.Column(
                controls=[
                    ft.Row([article, qty, warehouse]),
                    ft.FilledButton("Провести", on_click=submit, style=ft.ButtonStyle(bgcolor=ACCENT)),
                ]
            ),
        )

    def _stock_tab(self) -> ft.Tab:
        self.refresh_table()
        return ft.Tab(
            text="Остатки",
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text("Остатки", size=20, weight=ft.FontWeight.W_600),
                        ft.Text("Первые строки номенклатуры из локального состояния.", color=TEXT_SECONDARY),
                        ft.Container(content=self.article_table, bgcolor=SURFACE, border_radius=12, padding=12),
                    ]
                ),
            ),
        )

    def _settings_tab(self) -> ft.Tab:
        db_url = ft.TextField(label="PostgreSQL URL", value=self.state.db_url, bgcolor=SURFACE)

        def save(_: ft.ControlEvent) -> None:
            self.state.db_url = db_url.value or ""
            self.storage.save(self.state)
            self.set_status("Настройки сохранены")

        return ft.Tab(
            text="Настройки",
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    controls=[
                        ft.Text("Настройки", size=20, weight=ft.FontWeight.W_600),
                        db_url,
                        ft.FilledButton("Сохранить", on_click=save, style=ft.ButtonStyle(bgcolor=ACCENT)),
                    ]
                ),
            ),
        )

    def refresh_table(self) -> None:
        self.article_table.columns = [
            ft.DataColumn(ft.Text("Артикул")),
            ft.DataColumn(ft.Text("Название")),
            ft.DataColumn(ft.Text("Кол-во")),
        ]
        self.article_table.rows = [
            ft.DataRow(cells=[ft.DataCell(ft.Text(a)), ft.DataCell(ft.Text(n)), ft.DataCell(ft.Text(q))])
            for a, n, q in (self.state.article_rows or [])
        ]

    def set_status(self, text: str) -> None:
        self.status_text.value = text
        self.page.update()

    def handle_keyboard(self, event: ft.KeyboardEvent) -> None:
        key_map: dict[str, int] = {"F1": 0, "F2": 0, "F3": 1, "F4": 2, "F5": 3}
        if event.key in key_map and self.tabs_ref.current:
            self.tabs_ref.current.selected_index = key_map[event.key]
            self.page.update()


def main(page: ft.Page) -> None:
    WMSApp(page).run()


if __name__ == "__main__":
    runner = getattr(ft, "run", None)
    if callable(runner):
        runner(main)
    else:
        ft.app(main)
