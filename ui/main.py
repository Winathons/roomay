"""The UI half of this peg.

Compile it with `workpeg ui build ui/`, or watch it as you edit with
`workpeg ui serve ui/`.
"""
from workpeg.ui import Route, Router, Scaffold, Text
from dev_smoke import DevSmoke


class Home(Scaffold):
    def build(self):
        return Text("Hello from roomay")


class Main(Router):
    routes = [Route("/", Home), Route("/b/[business_id]/dev-smoke", DevSmoke)]
