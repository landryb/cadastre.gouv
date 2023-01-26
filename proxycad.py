#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

import logging
import os
import configparser
import xml.etree.ElementTree as ET
from requests.structures import CaseInsensitiveDict
from requests import get
from flask import Flask, Response, render_template, request, g, send_file, redirect
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from osgeo import gdal, ogr, osr

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
            g.ds = gdal.OpenEx(app.config.datasource, allowed_drivers = ['PostgreSQL'])
        else:
            g.ds = gdal.OpenEx(app.config.datasource)
        if g.ds is not None:
            g.layer = g.ds.GetLayerByName(app.config.couche_commune)
        if g.layer is None:
            app.logger.error("{} not found in {}".format(app.config.couche_commune, app.config.datasource))
            quit()
        # compute layer bbox so that we know the service extent for getcapabilities
        l93ext = g.layer.GetExtent()
        app.config.l93bbox = l93ext
        # reproject to WGS84
        s_srs = osr.SpatialReference()
        s_srs.ImportFromEPSG(2154)
        t_srs = osr.SpatialReference()
        t_srs.ImportFromEPSG(4326)
        t = osr.CoordinateTransformation(s_srs, t_srs)
        bl = t.TransformPoint(l93ext[0], l93ext[2])
        ur = t.TransformPoint(l93ext[1], l93ext[3])
        app.config.llbbox = (bl[0], bl[1], ur[0], ur[1])
    return g.layer

maxscale = 25000
app = Flask(__name__, template_folder=".")
init_app(app)

def empty_image(height, width, fmt, message=None):
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if message and height > 300 and width > 300:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
        img_draw = ImageDraw.Draw(canvas)
        box = img_draw.multiline_textsize(message, font=font)
        # calculate position
        x = (width - box[0]) // 2
        y = (height - box[1]) // 2
        img_draw.multiline_text((x, y), message, fill="red", font=font)
    img_io = BytesIO()
    canvas.save(img_io, fmt.split('/')[1].upper())
    img_io.seek(0)
    return send_file(img_io, mimetype=fmt)


def report_exception(message):
    app.logger.error("{}".format(message))
    return message, 405

# return a list of insee codes for a given bbox
def get_insee_for_bbox(xmin, ymin, xmax, ymax, epsg):
    layer = get_layer()
    comms = list()
    if epsg != '2154':
        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(float(xmax),float(ymin))
        ring.AddPoint(float(xmax),float(ymax))
        ring.AddPoint(float(xmin),float(ymax))
        ring.AddPoint(float(xmin),float(ymin))
        ring.AddPoint(float(xmax),float(ymin))
        poly = ogr.Geometry(ogr.wkbPolygon)
        poly.AddGeometry(ring)
        s_srs = osr.SpatialReference()
        s_srs.ImportFromEPSG(epsg)
        t_srs = osr.SpatialReference()
        t_srs.ImportFromEPSG(2154)
        poly.Transform(osr.CoordinateTransformation(s_srs, t_srs))
        layer.SetSpatialFilter(poly)
    else:
        layer.SetSpatialFilterRect(xmin, ymin, xmax, ymax)
    for feature in layer:
         comms.append(feature.GetField(app.config.champ_insee))
    layer.ResetReading()
    layer.SetSpatialFilter(None)
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
        get_layer()
        return Response(render_template(
            "getcap.xml.j2",
            proto=request.headers.get("X-Forwarded-Proto", "http"),
            host=request.headers.get("X-Forwarded-Host", "localhost"),
            l93bbox = app.config.l93bbox,
            llbbox = app.config.llbbox,
            reqpath=request.path,
        ), mimetype='text/xml')

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
        if fmt not in ('image/png'):
            return report_exception("Format d'image non pris en compte: {}".format(fmt))

        # validate height/width
        height = args.get("height", "")
        width = args.get("width", "")
        if not height.isnumeric() or not width.isnumeric():
            return report_exception("height and width should be numeric values")
        height = int(height)
        width = int(width)
        if width > 1280:
            return empty_image(height, width, fmt, "le service de la DGFiP ne supporte pas les images de plus de 1280px de large")

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
            app.logger.debug("{} {} (EPSG:{}) => 302 w/ {}".format(query, bbox, epsg, comms[0]))
            url = "https://inspire.cadastre.gouv.fr/scpc/{}/{}.wms?{}".format(app.config.apikey, comms[0], request.query_string.decode('unicode_escape'))
            return redirect(url, code=302)
        # do X queries
        else:
            app.logger.debug("{} {} (EPSG:{}) => merging for {}".format(query, bbox, epsg, comms))
            nb = 0
            for comm in comms:
                url = "https://inspire.cadastre.gouv.fr/scpc/{}/{}.wms?transparent=true&{}".format(app.config.apikey, comm, request.query_string.decode('unicode_escape'))
                resp = get(url, args)
                if resp.status_code != 200:
                    app.logger.error("{} => {} (mimetype {})".format(url, resp.status_code, resp.headers.get('content-type')))
                    continue
                if query == "getfeatureinfo":
                    if args.get("info_format") == "application/vnd.ogc.gml":
                        root = ET.fromstring(resp.content)
                        for child in root:
                            # XX returns the first comm that gives a feature
                            if child.tag.endswith('member'):
                                return Response(resp.content, mimetype=resp.headers.get('content-type'))
                    # text/html
                    else:
                        # XX returns the first comm that gives a feature in the HTML (eg non-empty table)
                        if b"inspireId" in resp.content:
                            return Response(resp.content, mimetype=resp.headers.get('content-type'))
                else:
                    im = Image.open(BytesIO(resp.content))
                    if nb == 0:
                        out = im
                    else:
                        out = Image.alpha_composite(out, im)
                    nb += 1
            # if we're here, none of the GFI returned a feature - return the last resp ?
            if query == "getfeatureinfo":
                return Response(resp.content, mimetype=resp.headers.get('content-type'))
            img_io = BytesIO()
            outmode = fmt.split('/')[1].upper()
            out.save(img_io, outmode)
            img_io.seek(0)
            return send_file(img_io, mimetype=fmt)

    else:
        return report_exception("bbox, crs, width, height, layers & format parameters are mandatory for getmap")

if __name__ == "__main__":
    app.logger.setLevel(logging.DEBUG)
    app.run(debug=True)
else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
