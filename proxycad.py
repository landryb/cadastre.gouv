#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

import logging
import os
import configparser
from requests.structures import CaseInsensitiveDict
from requests import get
from flask import Flask, Response, render_template, request, g, send_file, redirect
from io import BytesIO
from PIL import Image
from osgeo import gdal

# read config file
def init_app(app):
    config = configparser.ConfigParser()
    config.read('config.ini')
    app.logger.debug(config)
    if 'gdal' in config.sections():
        app.config.datasource = config['gdal'].get('datasource')
        app.config.couche_commune = config['gdal'].get('layer')
        app.config.champ_insee = config['gdal'].get('insee')
        app.config.champ_geom = config['gdal'].get('geom')
    if 'dgfip' in config.sections():
        app.config.apikey = config['dgfip'].get('apikey')

# open gdal data source, return layer
def get_layer():
    if "layer" not in g:
        gdal.UseExceptions()
        if app.config.datasource.startswith("PG:"):
            ds = gdal.OpenEx(app.config.datasource, allowed_drivers = ['PostgreSQL'])
        else:
            ds = gdal.OpenEx(app.config.datasource)
        if ds is not None:
            g.layer = ds.GetLayerByName(app.config.couche_commune)
        if g.layer is None:
            pass
    return g.layer

maxscale = 25000
app = Flask(__name__, template_folder=".")
init_app(app)

def report_exception(message):
    app.logger.error("{}".format(message))
    return message, 405

# return a list of insee codes for a given bbox
def get_insee_for_bbox(xmin, ymin, xmax, ymax, epsg):
    layer = get_layer()
    comms = list()
    layer.ExecuteSQL("SELECT {} FROM {} WHERE ST_Intersects({}, "
        "ST_Transform(ST_MakeEnvelope({},{},{},{},{}), 2154)) LIMIT 10".format(app.config.champ_insee, app.config.couche_commune, app.config.champ_geom, xmin, ymin, xmax, ymax, epsg))
    for feature in layer:
#    layer.SetSpatialFilter(ogr.CreateGeometryFromWkt(wkt))
         comms.append(feature.GetField(app.config.champ_insee))
#    layer.ResetReading()
#    layer.SetSpatialFilter(None)
    return comms

@app.route("/", methods=["GET"], defaults={"u_path": ""})
@app.route("/<path:u_path>", methods=["GET"])
def main(u_path):

    args = CaseInsensitiveDict(request.args)
    service = args.get("service", "").lower()
    if not service:
        return report_exception("service parameter is mandatory")
    if service != "wms":
        return report_exception("unknown service type, only wms is supported")

    query = args.get("request", "").lower()
    if not query:
        return report_exception("request parameter is mandatory")
    if (
        query != "getcapabilities"
        and query != "getmap"
        and query != "getfeatureinfo"
    ):
        return report_exception(
            "unknown request type {}, only getcapabilities, getmap and getfeatureinfo are supported".format(
                query
            ),
        )

    if query == "getcapabilities":
        return Response(render_template(
            "getcap.xml.j2",
            proto=request.headers.get("X-Forwarded-Proto", "http"),
            host=request.headers.get("X-Forwarded-Host", "localhost"),
            reqpath=request.path,
        ), mimetype='text/xml')
    if query == "getfeatureinfo":
        # todo
        pass

    # now service is getmap, check all mandatory params
    if all(key in args for key in ("bbox", "crs", "width", "height", "layers", "format")):

        # validate crs
        crs = args.get("crs")
        epsg = 2154
        if ':' in crs:
            x = crs.split(':')[1]
            if x.isnumeric():
                epsg = int(x)
        # validate format
        fmt = args.get("format", "").lower()
        if fmt not in ('image/png', 'image/jpeg', 'image/gif'):
            return report_exception("Format d'image non pris en compte: {}".format(fmt))

        # validate height/width
        height = args.get("height", "")
        width = args.get("width", "")
        if not height.isnumeric() or not width.isnumeric():
            return report_exception("height and width should be numeric values")
        height = int(height)
        width = int(width)

        # validate that bbox only has 4 values
        bbox = args.get("bbox")
        if bbox.count(",") != 3:
            return report_exception("bbox should look like xmin,ymin,xmax,ymax with only numeric values")
        [sxmin, symin, sxmax, symax] = map(lambda s: s.split(".")[0], bbox.split(","))
#        if not isint(sxmin) or not isint(symin) or not isint(sxmax) or not isint(symax):
#            return report_exception("bbox should look like xmin,ymin,xmax,ymax with only numeric values")
        # validate scale
        scale = (float(sxmax) - float(sxmin))/(width * 0.00028)
        if scale > maxscale:
            return report_exception("echelle non autorisée ({} > {})".format(scale, maxscale))

        comms = get_insee_for_bbox(sxmin, symin, sxmax, symax, epsg)
        # matche a single comm, return a 302 with the right url
        if len(comms) == 1:
            app.logger.debug("{} => 302 w/ {}".format(bbox, comms[0]))
            url = "https://inspire.cadastre.gouv.fr/scpc/{}/{}.wms?{}".format(app.config.apikey, comms[0], request.query_string.decode('unicode_escape'))
            return redirect(url, code=302)
        # do X queries
        else:
            app.logger.debug("{} => merging for {}".format(bbox, comms))
            nb = 0
            for comm in comms:
                url = "https://inspire.cadastre.gouv.fr/scpc/{}/{}.wms?transparent=true&{}".format(app.config.apikey, comm, request.query_string.decode('unicode_escape'))
                resp = get(url, args)
                app.logger.debug("{} => {} (mimetype {})".format(url, resp.status_code, resp.mimetype))
                if resp.status_code != 200:
                    continue

                im = Image.open(BytesIO(resp.content))
                if nb == 0:
                    out = im
                else:
                    out = Image.alpha_composite(out, im)
                nb += 1
            return send_file(im, mimetype=fmt)

    else:
        return report_exception("bbox, crs, width, height, layers & format parameters are mandatory for getmap")

if __name__ == "__main__":
    app.run(debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
