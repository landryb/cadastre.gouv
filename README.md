# Proxy cadastre.gouv
Proxy permettant à partir d'un seul point d'accès de disposer de l'intégralité des flux WMS (un par commune) depuis cadastre.gouv.fr...
Ce service s'utilise comme une sercice OGC de type WMS. exemple : (http://kartenn.region-bretagne.fr/ws/cadastre/france.wms?SERVICE=WMS&REQUEST=GetCapabilities)
Il est recommandé d'utiliser une clé premium cadastre.gouv.fr : (https://www.cadastre.gouv.fr/scpc/afficherServiceWMS.do?CSRF_TOKEN=0QSM-EWVC-RJ2P-ETJA-FS83-ZWFS-GQES-BYMR)

## différences avec https://github.com/spelhate/proxycad
Ce proxy est très fortement inspiré par https://github.com/spelhate/proxycad, mais avec comme différences:
- réécrit en python/WSGI, s'intègre mieux avec l'infrastructure du CRAIG
- configuration dans un fichier à part
- support de l'interrogation des couches `CP.CadastralParcel` et `BU.Building` via l'opération `GetFeatureInfo`
- possibilité d'utiliser n'importe quelle source de donnée GDAL/OGR pour la couche d'intersection des communes

## Prérequis
Disposer d'une couche spatiale des communes de la zone souhaitée (une région,
la france..) disposant à minima des champs suivants:
 - code INSEE
 - géométrie

la couche ADMINEXPRESS COG CARTO (https://geoservices.ign.fr/adminexpress) est
un bon exemple, mais on peut aussi utiliser les communes d'openstreetmap comme
le fait par défaut https://github.com/spelhate/proxycad

## Paramétrage
### Editer la configuration
 - clé premium,
 - chemin du fichier contenant la couche (ou chaine de connection postgis)
 - nom de la couche communale
 - nom du champ insee
 - nom du champ contenant la géométrie de la commune

### Editer le fichier capabilities.xml
 - Modifier les emprises si besoin

## Déploiement

## Utilisation

Exemple d'utilisation : (http://geobretagne.fr/mapfishapp/map/b391ec0966a3ff4da4c78bcfbc5688bf)
