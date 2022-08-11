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

DistrictOutline = "/Users/Jonathan/Downloads/GA6Outline/GA6Outline.shp"
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



counties = "/Users/Jonathan/Downloads/GA6Counties/GA6Counties.shp"
countiesData = gpd.read_file(counties)
countiesindex = countiesData.set_index('id')['RepMa']
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
        fields=["NAME","TotalPop","WhitePct","CoCom","ScoBoe"],
        aliases=["County: ", "Population: ","Percentage White: ","County Commissioners: ", "School Board Members: "],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "Counties",
    show = True,
    control = True
    ).add_to(m)

cities = "/Users/Jonathan/Downloads/GA6Cities/GA6Cities.shp"
citiesData = gpd.read_file(cities)
citiesindex = citiesData.set_index('id')['RepMa']
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
        fields=["NAME","TotalPop","WhitePct", "Mayor","CitCo"],
        aliases=["City: ", "Population: ","Percentage White: ","Mayor: ", "City Council: "],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "Cities",
    show = False,
    control = True
    ).add_to(m)

stateh = "/Users/Jonathan/Downloads/GA6StateHouse/GA6StateHouse.shp"
statehData = gpd.read_file(stateh)
statehindex = statehData.set_index('id')['RepMa']
folium.GeoJson(
    statehData,
    style_function=lambda feature: {
        'fillColor': linear(statehindex[feature['properties']['id']]),
        'fillOpacity' : 0.75,
        'color' : 'black',
        'weight' : 0.5,
        },
    highlight_function = highlight_function,
    tooltip=folium.features.GeoJsonTooltip(
        fields=["NAME","Incumbent","TotalPop","WhitePct"],
        aliases=["District: ", "Representative/Election: ", "Population: ","Percentage White: ",],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "State House",
    show = False,
    control = True
    ).add_to(m)

states = "/Users/Jonathan/Downloads/GA6StateSenate/GA6StateSenate.shp"
statesData = gpd.read_file(states)
statesindex = statesData.set_index('id')['RepMa']
folium.GeoJson(
    statesData,
    style_function=lambda feature: {
        'fillColor': linear(statesindex[feature['properties']['id']]),
        'fillOpacity' : 0.75,
        'color' : 'black',
        'weight' : 0.5,
        },
    highlight_function = highlight_function,
    tooltip=folium.features.GeoJsonTooltip(
        fields=["NAME","Incumbent","TotalPop","WhitePct"],
        aliases=["District: ", "Senator/Election: ", "Population: ","Percentage White: ",],
        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;") 
    ),
    name = "State Senate",
    show = False,
    control = True
    ).add_to(m)






folium.LayerControl().add_to(m)
m.save("/Users/Jonathan/Downloads/Ga6Officials.html")
