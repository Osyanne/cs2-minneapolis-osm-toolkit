"""Source registry — explicit dict populated by importing each city source module.

Adding a new city = create `<slug>.py` in this dir + add to SOURCES dict below.
"""
from official_zoning.sources import minneapolis

SOURCES = {
    "minneapolis": minneapolis,
}
