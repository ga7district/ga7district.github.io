# import the folium library
import sys
import json
import folium
import pandas as pd
import geopandas as gpd
import branca.colormap as cm 
# initialize the map and store it in a m object
m = folium.Map(location=[34.2997601359877, -84.261], zoom_start=10)
folium.TileLayer('stamentoner').add_to(m)
folium.TileLayer('cartodbpositron').add_to(m)

linear = cm.LinearColormap(['blue','white','red'], vmin=-1,vmax=1)
linear.caption = 'Republican Margin (%)'
m.add_child (linear)



highlight_function = lambda x: {'fillColor': '#000000', 
                                'color':'#000000', 
                                'fillOpacity': 0.50, 
                                'weight': 3}

DistrictOutline = "/Users/Jonathan/Downloads/ga7outline.shp"
DistrictOutlineData = gpd.read_file(DistrictOutline)
folium.GeoJson(
    DistrictOutlineData,
    style_function=lambda feature: {
        'fillColor': "white",
        'fillOpacity' : 0,
        'color' : 'black',
        'weight' : 2,
        },
    name = "District Outline",
    show = True,
    control = False
    ).add_to(m)



counties = "/Users/Jonathan/Downloads/ga7countiesSHP.shp"
countiesData = gpd.read_file(counties)
countiesindex = countiesData.set_index('id')['RepMar']
folium.GeoJson(
    countiesData,
    style_function=lambda feature: {
        'fillColor': linear(countiesindex[feature['properties']['id']]),
        'fillOpacity' : 0.75,
        'color' : 'black',
        'weight' : 0.5,
        },
    highlight_function = highlight_function,
    tooltip=folium.features.GeoJsonTooltip(
        fields=["NAME","TotalPop","RepMar"],
        aliases=["County: ", "Population: ","Republican Margin Percentage: "],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "Counties",
    show = True,
    control = True
    ).add_to(m)

cities = "/Users/Jonathan/Downloads/ga7citiesSHP.shp"
citiesData = gpd.read_file(cities)
citiesindex = citiesData.set_index('id')['RepMar']
folium.GeoJson(
    citiesData,
    style_function=lambda feature: {
        'fillColor': linear(citiesindex[feature['properties']['id']]),
        'fillOpacity' : 0.75,
        'color' : 'black',
        'weight' : 0.5,
        },
    highlight_function = highlight_function,
    tooltip=folium.features.GeoJsonTooltip(
        fields=["NAME","TotalPop", "RepMar"],
        aliases=["City: ", "Population: ", "Republican Margin Percentage: "],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "Cities",
    show = False,
    control = True
    ).add_to(m)


stateprec = "/Users/Jonathan/Downloads/ga7precinctsSHP.shp"
stateprecdata = gpd.read_file(stateprec)
precindex = stateprecdata.set_index('id')['RepMar']
folium.GeoJson(
    stateprecdata,
    style_function=lambda feature: {
        'fillColor': linear(precindex[feature['properties']['id']]),
        'fillOpacity' : 0.75,
        'color' : 'black',
        'weight' : 0.5,
        },
    highlight_function = highlight_function,
    tooltip=folium.features.GeoJsonTooltip(
        fields=["NAME","TotalPop", "RepMar"],
        aliases=["Precinct: ", "Population: ","Republican Margin Percentage: "],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "Precinct Results",
    show = False,
    control = True
    ).add_to(m)





folium.LayerControl().add_to(m)
m.save("/Users/Jonathan/Downloads/Ga7Interactive.html")
