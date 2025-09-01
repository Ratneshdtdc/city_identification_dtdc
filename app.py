# app.py
# -------------------------------------------------------------
# Streamlit app to fetch city boundary from OSM, edit on map,
# and save/download the updated boundary (GeoJSON).
# -------------------------------------------------------------
# Requirements (requirements.txt):
# streamlit
# osmnx
# geopandas
# shapely
# folium
# streamlit-folium
#
# Run: streamlit run app.py
# -------------------------------------------------------------

import json
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw, Fullscreen


st.set_page_config(page_title="City Boundary Editor", layout="wide")


# ---------- helpers ----------
@st.cache_data(show_spinner=True)
def fetch_city_boundary(city_name: str) -> dict:
    """
    Fetch a city's administrative boundary as a single (multi)polygon GeoJSON Feature.
    """
    # Pull any admin boundary polygon OSM knows for that place
    gdf = ox.geocode_to_gdf(city_name, which_result=1, by_osmid=False)
    # Some places return multiple parts -> dissolve to single row
    if len(gdf) > 1:
        gdf = gdf.dissolve()

    gdf = gdf.to_crs(4326)  # ensure WGS84 for web maps
    geom = gdf.iloc[0].geometry

    # Normalize to (Multi)Polygon only (drop boundaries/lines if any)
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            raise ValueError("No polygon geometry found for this place.")
        geom = polys[0]

    if geom.geom_type == "Polygon":
        out_geom = geom
    elif geom.geom_type == "MultiPolygon":
        out_geom = geom
    else:
        raise ValueError(f"Unsupported geometry type: {geom.geom_type}")

    feature = {
        "type": "Feature",
        "properties": {"name": city_name},
        "geometry": mapping(out_geom),
    }
    return feature


def centroid_latlon(geom) -> tuple[float, float]:
    c = geom.centroid
    return float(c.y), float(c.x)


def to_geodataframe(geojson_feature: dict) -> gpd.GeoDataFrame:
    g = shape(geojson_feature["geometry"])
    return gpd.GeoDataFrame(
        {"name": [geojson_feature["properties"].get("name", "edited")]},
        geometry=[g],
        crs="EPSG:4326",
    )


def normalize_drawn_features(output: dict, fallback_feature: dict) -> dict:
    """
    Turn st_folium draw output into a single GeoJSON Feature (Multi)Polygon.
    - If multiple polygons were drawn, union them.
    - If nothing was drawn/edited, return fallback (original) feature.
    """
    features = []

    # streamlit-folium v0.18+/v0.20 payloads vary; handle common keys
    for key in ("all_drawings", "all_features"):
        drawn = output.get(key)
        if drawn and isinstance(drawn, list):
            for f in drawn:
                try:
                    # some payloads store geojson under "geometry" only
                    if "type" in f and f["type"] == "Feature":
                        features.append(f)
                    elif "geometry" in f:
                        features.append({"type": "Feature", "properties": {}, "geometry": f["geometry"]})
                except Exception:
                    pass

    # If edit mode altered the original layer, folium may return "last_active_drawing"
    lad = output.get("last_active_drawing")
    if lad and isinstance(lad, dict) and "geometry" in lad:
        features.append({"type": "Feature", "properties": {}, "geometry": lad["geometry"]})

    # Nothing drawn → keep original
    if not features:
        return fallback_feature

    # Collect polygonal geometries
    geoms = []
    for f in features:
        try:
            geom = shape(f["geometry"])
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                geoms.append(geom)
        except Exception:
            continue

    if not geoms:
        return fallback_feature

    # Union into a single geometry
    gdf = gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326").dissolve()
    merged = gdf.iloc[0].geometry
    # Ensure polygonal
    if merged.geom_type not in ("Polygon", "MultiPolygon"):
        return fallback_feature

    # build single feature
    return {
        "type": "Feature",
        "properties": {"name": fallback_feature["properties"].get("name", "edited")},
        "geometry": mapping(merged),
    }


def save_geojson_feature(feature: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    name = feature["properties"].get("name", "boundary").replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = directory / f"{name}_edited_{ts}.geojson"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feature, f, ensure_ascii=False)
    return path


# ---------- UI ----------
st.title("🗺️ City Boundary Editor (OSM)")

with st.sidebar:
    st.header("⚙️ Settings")
    city = st.text_input("City / Place name", value="Bengaluru, India", help="Any place OSM can geocode.")
    fetch_btn = st.button("Fetch Boundary")
    st.markdown("---")
    uploaded = st.file_uploader("Or upload your own GeoJSON", type=["geojson", "json"], help="Optional: Start from a file you already have.")
    st.markdown("---")
    st.caption("Tip: Use the ✏️ Edit tool on the map to drag/extend vertices of the boundary.")

# Load base feature (from OSM or upload)
feature = None
error_msg = None

if uploaded is not None:
    try:
        data = json.load(uploaded)
        # Accept Feature or FeatureCollection; normalize to single Feature
        if data.get("type") == "Feature":
            feature = data
        elif data.get("type") == "FeatureCollection" and data.get("features"):
            # dissolve collection into one polygon
            gdf = gpd.GeoDataFrame.from_features(data, crs="EPSG:4326")
            gdf = gdf.dissolve()
            geom = gdf.iloc[0].geometry
            feature = {"type": "Feature", "properties": {"name": "uploaded"}, "geometry": mapping(geom)}
        else:
            error_msg = "Invalid GeoJSON structure."
    except Exception as e:
        error_msg = f"Failed to read GeoJSON: {e}"

elif fetch_btn or city:
    try:
        feature = fetch_city_boundary(city)
    except Exception as e:
        error_msg = f"OSM lookup failed: {e}. Try a more specific name (e.g., 'City, Country')."

if error_msg:
    st.error(error_msg)

if feature:
    # Center map on boundary centroid
    g = shape(feature["geometry"])
    lat, lon = centroid_latlon(g)

    # Build folium map
    m = folium.Map(location=[lat, lon], zoom_start=10, tiles="cartodbpositron", control_scale=True)
    Fullscreen().add_to(m)

    # Add the original boundary layer
    folium.GeoJson(
        feature,
        name="Original Boundary",
        style_function=lambda x: {"fill": True, "fillOpacity": 0.1, "weight": 2},
        tooltip=feature["properties"].get("name", "boundary"),
        show=True,
    ).add_to(m)

    # Draw control (enable edit of existing + add polygons if needed)
    draw = Draw(
        export=False,
        edit_options={"poly": {"allowIntersection": False}, "featureGroup": "drawnItems"},
        draw_options={
            "polyline": False,
            "rectangle": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "polygon": True,  # allow adding polygons (unioned with original when saving)
        },
    )
    draw.add_to(m)

    st.markdown("### ✏️ Edit the boundary on the map")
    out = st_folium(m, width=None, height=650, use_container_width=True)

    # Convert drawn/edited results to a single Feature
    edited_feature = normalize_drawn_features(out or {}, fallback_feature=feature)
    edited_gdf = to_geodataframe(edited_feature)

    st.markdown("### 💾 Save / Download")
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        # Server-side save
        if st.button("Save to server"):
            save_path = save_geojson_feature(edited_feature, Path("saved_boundaries"))
            st.success(f"Saved: {save_path}")

    with col2:
        # Download button
        pretty_geojson = json.dumps(edited_feature, ensure_ascii=False, indent=2)
        st.download_button(
            label="Download GeoJSON",
            data=pretty_geojson.encode("utf-8"),
            file_name=f"{edited_feature['properties'].get('name','boundary')}_edited.geojson",
            mime="application/geo+json",
        )

    with col3:
        st.dataframe(edited_gdf.drop(columns="geometry"))
        st.caption("Preview of properties. Geometry saved as GeoJSON.")

    st.markdown(
        """
        **Notes**
        - Use the **Edit** tool on the existing polygon to drag vertices/edges and extend the area.
        - You can also draw additional polygons; the app unions them into a single boundary when saving.
        - Output CRS is **EPSG:4326 (WGS84)**, compatible with most GIS tools.
        """
    )
else:
    st.info("Enter a city name (e.g., **Bhopal, India**) and click **Fetch Boundary**, or upload a GeoJSON to start editing.")
