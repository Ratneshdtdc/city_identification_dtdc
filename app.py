import streamlit as st
import osmnx as ox
import geopandas as gpd
from shapely.geometry import mapping
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw
import json

st.set_page_config(page_title="Editable OSM Boundary", layout="wide")
st.title("🗺️ Editable OSM City Boundary")

city = st.text_input("City name", value="Bengaluru, India")

if st.button("Fetch Boundary"):
    # Fetch boundary from OSM
    gdf = ox.geocode_to_gdf(city, which_result=1)
    gdf = gdf.to_crs(4326)
    geom = gdf.iloc[0].geometry

    feature = {
        "type": "Feature",
        "properties": {"name": city},
        "geometry": mapping(geom)
    }

    centroid = geom.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=10, tiles="cartodbpositron")

    # Add original boundary to a FeatureGroup called "drawnItems"
    fg = folium.FeatureGroup(name="drawnItems")
    folium.GeoJson(
        feature,
        name="boundary",
        style_function=lambda x: {"fillColor": "blue", "color": "black", "weight": 2, "fillOpacity": 0.1},
    ).add_to(fg)
    fg.add_to(m)

    # Attach Draw plugin (edit only existing)
    draw = Draw(
        draw_options=False,
        edit_options={"featureGroup": "drawnItems"}  # <-- must match FeatureGroup name
    )
    draw.add_to(m)

    st.markdown("### Drag the boundary vertices to adjust it 👇")
    output = st_folium(m, width=700, height=500, key="map1")

    edited = None
    if output:
        if "last_active_drawing" in output and output["last_active_drawing"]:
            edited = output["last_active_drawing"]
        elif "all_drawings" in output and output["all_drawings"]:
            edited = output["all_drawings"][-1]

    if edited:
        st.success("Edited boundary captured ✅")
        st.json(edited)
        st.download_button(
            "Download Edited GeoJSON",
            data=json.dumps(edited),
            file_name=f"{city.replace(',','').replace(' ','_')}_edited.geojson",
            mime="application/geo+json"
        )
