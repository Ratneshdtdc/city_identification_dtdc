import streamlit as st
import osmnx as ox
import geopandas as gpd
import json
from shapely.geometry import mapping
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw

st.set_page_config(page_title="Editable OSM Boundary", layout="wide")

st.title("🗺️ Editable OSM City Boundary")

city = st.text_input("City name", value="Bengaluru, India")

if st.button("Fetch Boundary"):
    # get OSM boundary
    gdf = ox.geocode_to_gdf(city, which_result=1)
    gdf = gdf.to_crs(4326)
    geom = gdf.iloc[0].geometry
    
    # turn into geojson feature
    feature = {
        "type": "Feature",
        "properties": {"name": city},
        "geometry": mapping(geom)
    }

    # center map
    centroid = geom.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=10, tiles="cartodbpositron")

    # create a FeatureGroup with the boundary
    fg = folium.FeatureGroup(name="Editable Boundary", show=True)
    folium.GeoJson(
        feature,
        name="boundary",
        style_function=lambda x: {"fillColor": "#blue", "color": "black", "weight": 2, "fillOpacity": 0.1},
    ).add_to(fg)
    fg.add_to(m)

    # add Draw plugin: edit only existing boundary
    Draw(
        draw_options=False,  # don’t allow new shapes
        edit_options={"featureGroup": fg}
    ).add_to(m)

    st.markdown("### Drag the boundary vertices to adjust it 👇")
    output = st_folium(m, width=None, height=600, key="map")

    # capture edited geojson
    edited = None
    if output:
        if "last_active_drawing" in output and output["last_active_drawing"]:
            edited = output["last_active_drawing"]
        elif "all_drawings" in output and output["all_drawings"]:
            edited = output["all_drawings"][-1]

    if edited:
        st.success("Edited boundary captured ✅")
        st.json(edited)

        # download button
        st.download_button(
            "Download Edited GeoJSON",
            data=json.dumps(edited),
            file_name=f"{city.replace(',','').replace(' ','_')}_edited.geojson",
            mime="application/geo+json"
        )
