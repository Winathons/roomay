"""The UI half of this peg.

Compile it with `workpeg ui build ui/`, or watch it as you edit with
`workpeg ui serve ui/`.
"""
from workpeg.ui import Route, Router, Scaffold, Text
from hotel_data import HotelData


class Home(Scaffold):
    def build(self):
        return Text("Roomay reception is available inside an authenticated Workpeg business.")


class Main(Router):
    routes = [
        Route("/", Home),
        Route("/b/[business_id]/reception", HotelData),
    ]
