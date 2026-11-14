"""Native Workpeg routes for ROOMAY.

The Workpeg business workspace is staff-authenticated and read-only. Guest
identity is not inferred from a Workpeg login, URL, or room number. Local QA
routes and their synthetic state live in ``tools.guest_chat_demo`` only.
"""
from workpeg.ui import (
    App, Column, Container, Link, Outlet, Route, Router, Shell, Text, Theme,
    biz_url,
)
from workpeg.ui.scaffold import NavItem, Scaffold
from hotel_data import HotelData


class Home(App):
    """Unscoped entry point: it cannot know which business the user selected."""

    def build(self):
        return Container(
            Column(
                Text("ROOMAY", variant="display", weight="bold"),
                Text("Hotel operations in Workpeg", variant="heading"),
                Text(
                    "Sign in to Workpeg and open ROOMAY from the Apps list "
                    "inside the intended business. Your business context is "
                    "selected by Workpeg; ROOMAY does not guess or hardcode it.",
                    tone="muted",
                ),
                Text(
                    "The staff workspace provides the authenticated, "
                    "read-only Reception view. Guest stay access requires a "
                    "separate verified guest identity and is not enabled in "
                    "this Workpeg session.",
                    tone="muted",
                ),
                gap=16,
                align="stretch",
            ),
            padding=24,
        )


class AppShell(Shell):
    """Authenticated Workpeg chrome around the business-scoped pages."""

    def build(self):
        return Scaffold(
            NavItem("Workspace home", biz_url("/"), icon="home"),
            NavItem("Reception", biz_url("/reception"), icon="layout-dashboard"),
            NavItem("Guest access status", biz_url("/stay"), icon="user"),
            main=Outlet(),
        )


class WorkspaceHome(App):
    """Business-scoped navigation and truthful feature availability."""

    def build(self):
        return Container(
            Column(
                Text("ROOMAY workspace", variant="display", weight="bold"),
                Text(
                    "Choose an available workspace for this authenticated "
                    "Workpeg business.", tone="muted",
                ),
                Container(
                    Column(
                        Text("Reception", variant="heading", weight="semibold"),
                        Text(
                            "View the verified, read-only hotel snapshot. "
                            "This workspace does not create or change records.",
                            tone="muted",
                        ),
                        Link("Open Reception", href=biz_url("/reception")),
                        gap=12,
                        align="stretch",
                    ),
                    padding=20,
                    color="#ffffff",
                    radius=14,
                ),
                Container(
                    Column(
                        Text("Workpeg AI chat", variant="heading", weight="semibold"),
                        Text(
                            "Workpeg's built-in chat can be opened for general "
                            "assistance. ROOMAY has not registered custom AI "
                            "actions or a verified hotel-facts source, so this "
                            "chat cannot look up Roomay stays, submit a request, "
                            "or report an operational status.",
                            tone="muted",
                        ),
                        Link("Open Workpeg AI chat", href=biz_url("/chats/new")),
                        gap=12,
                        align="stretch",
                    ),
                    padding=20,
                    color="#ffffff",
                    radius=14,
                ),
                Container(
                    Column(
                        Text("Guest stay access", variant="heading", weight="semibold"),
                        Text(
                            "Guest identity verification is not connected to this "
                            "native Workpeg app. No guest stay details or request "
                            "actions are available here.",
                            tone="muted",
                        ),
                        Link("View guest-access status", href=biz_url("/stay")),
                        gap=12,
                        align="stretch",
                    ),
                    padding=20,
                    color="#ffffff",
                    radius=14,
                ),
                gap=18,
                align="stretch",
            ),
            padding=24,
        )


class GuestAccessUnavailable(App):
    """Safe destination for the former missing business-scoped Guest route."""

    def build(self):
        return Container(
            Column(
                Text("Guest stay access is unavailable", variant="display", weight="bold"),
                Text(
                    "A Workpeg business sign-in does not verify a hotel guest "
                    "or an active stay. ROOMAY has not connected a trusted guest "
                    "invitation or contact-verification service to this route.",
                    tone="muted",
                ),
                Text(
                    "No room, guest, reservation, stay, or request records were loaded. "
                    "No request was created. Contact the hotel through its "
                    "approved guest channel for assistance.",
                    tone="muted",
                ),
                Link("Return to Reception", href=biz_url("/reception")),
                gap=16,
                align="stretch",
            ),
            padding=24,
        )


class Main(Router):
    theme = Theme(
        primary="#174c3b",
        primary_fg="#ffffff",
        fg="#18221e",
        muted="#66716b",
        page="#f6f7f4",
        bg="#ffffff",
        border="#e5e9e4",
        radius="12px",
        font='"Inter", sans-serif',
    )
    fonts = [
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ]
    routes = [
        Route("/", Home),
        Shell(AppShell, "/b/[business_id]", [
            Route("/", WorkspaceHome),
            Route("/reception", HotelData),
            Route("/reception/[workspace]", HotelData),
            Route("/stay", GuestAccessUnavailable),
        ]),
    ]
