"""The UI half of this peg.

Compile it with `workpeg ui build ui/`, or watch it as you edit with
`workpeg ui serve ui/`.
"""
from workpeg.ui import Route, Router, Scaffold, Text, Theme
from hotel_data import HotelData


class Home(Scaffold):
    def build(self):
        return Text("Roomay reception is available inside an authenticated Workpeg business.")


class Main(Router):
    theme = Theme(
        primary="#2d6a4f",
        primary_fg="#ffffff",
        fg="#111827",
        muted="#5b6670",
        page="#f7f9f6",
        bg="#ffffff",
        border="#dce7e2",
        radius="14px",
        font='"Plus Jakarta Sans", sans-serif',
    )
    fonts = [
        "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap",
    ]
    routes = [
        Route("/", Home),
        Route("/b/[business_id]/reception", HotelData),
    ]
