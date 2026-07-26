import os
import dash_bootstrap_components as dbc
from dash import Dash, dcc, html, callback, ctx
from dash.dependencies import Input, Output, State

from app.auth import configure_auth
from app.data import get_engine
# Import pages at module load so their @callback definitions register with Dash
# before the server starts serving the callback dependency graph.
from app.pages import activities, glossary, overview, settings, weekly


def _brand(app: Dash):
    """Modern wordmark: gradient pulse badge + two-tone 'Enduralytics'."""
    return html.A(
        [
            html.Img(src=app.get_asset_url("logo.svg"), className="brand-logo__badge"),
            html.Span(
                [
                    html.Span("Endura", className="brand-logo__accent"),
                    html.Span("lytics", className="brand-logo__rest"),
                ],
                className="brand-logo__wordmark",
            ),
        ],
        href="/",
        className="brand-logo navbar-brand",
    )


def create_app() -> Dash:
    """Create and configure the Dash app with multi-page support."""
    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
    )
    app.title = "Enduralytics"
    app._favicon = "logo.svg"

    # Attach the single-user passcode gate to the underlying Flask server.
    configure_auth(app.server)

    engine = get_engine()

    app.layout = html.Div([
        dcc.Location(id="url", refresh=False),
        dbc.Navbar(
            dbc.Container(
                [
                    _brand(app),
                    dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),
                    dbc.Collapse(
                        dbc.Nav([
                            dbc.NavLink("Overview", href="/", active="exact"),
                            dbc.NavLink("Weekly", href="/weekly", active="exact"),
                            dbc.NavLink("Activities", href="/activities", active="exact"),
                            dbc.NavLink("Glossary", href="/glossary", active="exact"),
                            dbc.NavLink("Settings", href="/settings", active="exact"),
                        ], navbar=True, className="ms-auto"),
                        id="navbar-collapse",
                        is_open=False,
                        navbar=True,
                    ),
                ],
                fluid=True,
            ),
            color="dark",
            dark=True,
            expand="lg",
            className="mb-4",
        ),
        html.Div(id="page-content"),
    ])

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
    )
    def display_page(pathname):
        """Display the appropriate page based on the URL pathname."""
        if pathname == "/activities":
            return activities.layout()
        if pathname == "/weekly":
            return weekly.layout(engine)
        if pathname == "/glossary":
            return glossary.layout(engine)
        if pathname == "/settings":
            return settings.layout(engine)
        # Default overview page
        return overview.layout(engine)

    @app.callback(
        Output("navbar-collapse", "is_open"),
        Input("navbar-toggler", "n_clicks"),
        Input("url", "pathname"),
        State("navbar-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_navbar(n_clicks, pathname, is_open):
        """Open/close the mobile menu; close it after navigating to a page."""
        if ctx.triggered_id == "url":
            return False
        return not is_open

    return app


app = create_app()
server = app.server


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)

