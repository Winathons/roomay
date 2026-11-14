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
        primary="#181a1a",
        primary_fg="#ffffff",
        fg="#181a1a",
        muted="#737976",
        page="#f8f9f7",
        bg="#ffffff",
        border="#e8ebe8",
        radius="12px",
        font='"Inter", sans-serif',
    )
    fonts = [
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ]
    routes = [
        Route("/", Home),
        Route("/b/[business_id]/reception", HotelData),
        Route("/b/[business_id]/reception/[workspace]", HotelData),
    ]
