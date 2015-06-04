# -*- coding: utf-8 -*-
"""
/***************************************************************************
 NNJoin_nogui
                          NNJoin plugin to run from command-line
                          
Usage:
-------------- 
from NNJoin_nogui import runnogui
NNinst = runnogui(inputvectorlayer, joinvectorlayer,
                 outputlayername, approximateinputgeom, joinprefix,
                 usejoinlayerapproximation, usejoinlayerindex)
NNinst.run()
--------------


 Nearest neighbour spatial join
                             -------------------
        begin                : 2014-09-04
        git sha              : $Format:%H$
        copyright            : (C) 2014 by Håvard Tveite
        email                : havard.tveite@nmbu.no
        
        edited by            : Dominic Keller
        email                : dominicjkeller@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

#from qgis.core import *
from qgis.core import QgsMessageLog, QgsMapLayerRegistry, QGis
from qgis.core import QgsVectorLayer, QgsFeature, QgsSpatialIndex
from qgis.core import QgsFeatureRequest, QgsField, QgsGeometry
from qgis.core import QgsRectangle, QgsCoordinateTransform

#from processing import *
from PyQt4 import QtCore
from PyQt4.QtCore import QCoreApplication, QVariant


class runnogui:
    '''The worker that does the heavy lifting.
    /* QGIS offers spatial indexes to make spatial search more
     * effective.  QgsSpatialIndex will find the nearest index
     * (approximate) geometry (rectangle) for a supplied point.
     * QgsSpatialIndex will give correct results when searching
     * for the nearest neighbour of a point in a point data set.
     * So something has to be done for non-point data sets
     *
     * Non-point join data set:
     * A two pass search is performed.  First the index is used to
     * find the nearest index geometry (approximation - rectangle),
     * and then compute the actual distance to this geometry.
     * Then this rectangle is used to find all features in the join
     * data set that may be the closest feature to the given point.
     * For all the features is this candidate set, the actual
     * distance to the given point is calculated, and the nearest
     * feature is returned.
     *
     * Non-point input data set:
     * First the centroid of the non-point input geometry is
     * calculated.  Then the index is used to find the nearest
     * neighbour to this point (using the approximate index
     * geometry).
     * The distance vector to this feature, combined with the
     * bounding rectangle of the input feature is used to create a
     * search rectangle to find the candidate join geometries.
     * For all the features is this candidate set, the actual
     * distance to the given feature is calculated, and the nearest
     * feature is returned.
     *
     * Joins involving multi-geometry data sets are not supported
     * by a spatial index.
     *
    */
    '''
#    # Define the signals used to communicate back to the application
#    progress = QtCore.pyqtSignal(float)  # For reporting progress
#    status = QtCore.pyqtSignal(str)      # For reporting status
#    error = QtCore.pyqtSignal(str)       # For reporting errors
#    #killed = QtCore.pyqtSignal()
#    # Signal for sending over the result:
#    finished = QtCore.pyqtSignal(bool, object)

    def __init__(self, inputvectorlayer, joinvectorlayer,
                 outputlayername, approximateinputgeom, joinprefix,
                 usejoinlayerapproximation, usejoinlayerindex):
        """Initialise.

        Arguments:
        inputvectorlayer -- (QgsVectorLayer) The base vector layer
                            for the join
        joinvectorlayer -- (QgsVectorLayer) the join layer
        outputlayername -- (string) the name of the output memory
                           layer
        approximateinputgeom -- (boolean) should the input geometry
                                be approximated?  Is only be set for
                                non-single-point layers
        joinprefix -- (string) the prefix to use for the join layer
                      attributes in the output layer
        usejoinlayerindexapproximation -- (boolean) should the index
                             geometry approximations be used for the
                             join?
        usejoinlayerindex -- (boolean) should an index for the join
                             layer be used.  Will only use the index
                             geometry approximations for the join
        """

        # Set a variable to control the use of indexes and exact
        # geometries for non-point input geometries
        #self.nonpointexactindex = True
        self.nonpointexactindex = usejoinlayerindex

#        QtCore.QObject.__init__(self)  # Essential!
        # Creating instance variables from the parameters
        self.inpvl = inputvectorlayer
        self.joinvl = joinvectorlayer
        self.outputlayername = outputlayername
        self.approximateinputgeom = approximateinputgeom
        self.joinprefix = joinprefix
        self.usejoinlayerapprox = usejoinlayerapproximation
        # Check if the layers are the same (self join)
        self.selfjoin = False
        if self.inpvl is self.joinvl:
            # This is a self join
            self.selfjoin = True
        # Creating instance variables for the progress bar ++
        # Number of elements that have been processed - updated by
        # calculate_progress
        self.processed = 0
        # Current percentage of progress - updated by
        # calculate_progress
        self.percentage = 0
        # Flag set by kill(), checked in the loop
        self.abort = False
        # Number of features in the input layer - used by
        # calculate_progress
        self.feature_count = self.inpvl.featureCount()
        # The number of elements that is needed to increment the
        # progressbar - set early in run()
        self.increment = self.feature_count // 1000

    def run(self):
#        try:
        if self.inpvl is None or self.joinvl is None:
            print 'Layer is missing!'
            self.finished.emit(False, None)
            return
        #self.status.emit('Started!')
        # Check the geometry type and prepare the output layer
        geometryType = self.inpvl.geometryType()
        #self.status.emit('Input layer geometry type: ' +
        #                               str(geometryType))
        geometrytypetext = 'Point'
        if geometryType == QGis.Point:
            geometrytypetext = 'Point'
        elif geometryType == QGis.Line:
            geometrytypetext = 'LineString'
        elif geometryType == QGis.Polygon:
            geometrytypetext = 'Polygon'
        # Does the input vector contain multi-geometries?
        # Try to check the first feature
        # This is not used for anything yet
        self.inputmulti = False
        feats = self.inpvl.getFeatures()
        if feats is not None:
            #self.status.emit('#Input features: ' + str(feats))
            print '#Input features: ' + str(feats)
            testfeature = feats.next()
            feats.rewind()
            feats.close()
            if testfeature is not None:
                #self.status.emit('Input feature geometry: ' +
                #                 str(testfeature.geometry()))
                print 'Input feature geometry: ' + str(testfeature.geometry())
                if testfeature.geometry() is not None:
                    if testfeature.geometry().isMultipart():
                        self.inputmulti = True
                        geometrytypetext = 'Multi' + geometrytypetext
                    else:
                        pass
                else:
#                    self.status.emit('No geometry!')
#                    self.finished.emit(False, None)
                    print 'No geometry!'
                    return
            else:
#                self.status.emit('No input features!')
#                self.finished.emit(False, None)
                print 'No input features!'
                return
        else:
#            self.status.emit('getFeatures returns None for input layer!')
#            self.finished.emit(False, None)
            print 'getFeatures returns None for input layer!'
            return
        geomptext = geometrytypetext
        # Set the coordinate reference system to the input
        # layer's CRS
        if self.inpvl.crs() is not None:
            geomptext = (geomptext + "?crs=" +
                         str(self.inpvl.crs().authid()))
        outfields = self.inpvl.pendingFields().toList()
        #
        if self.joinvl.pendingFields() is not None:
            jfields = self.joinvl.pendingFields().toList()
            for joinfield in jfields:
                outfields.append(QgsField(self.joinprefix +
                                 str(joinfield.name()),
                                 joinfield.type()))
        else:
#            self.status.emit('Unable to get any join layer fields')
#            self.finished.emit(False, None)
            print 'Unable to get any join layer fields'
            return

        outfields.append(QgsField("distance", QVariant.Double))
        # Create a memory layer
        self.mem_joinl = QgsVectorLayer(geomptext,
                                        self.outputlayername,
                                        "memory")
        self.mem_joinl.startEditing()
        for field in outfields:
            self.mem_joinl.dataProvider().addAttributes([field])
        # For an index to be used, the input layer has to be a
        # point layer, the input layer geometries have to be
        # approximated to centroids, or the user has to have
        # accepted that a join layer index is used (for
        # non-point input layers).
        # (Could be extended to multipoint)
        if (self.inpvl.wkbType() == QGis.WKBPoint or
                self.inpvl.wkbType() == QGis.WKBPoint25D or
                self.approximateinputgeom or
                self.nonpointexactindex):
            # Create a spatial index to speed up joining
#            self.status.emit('Creating join layer index...')
            print 'Creating join layer index...'
            self.joinlind = QgsSpatialIndex()
            for feat in self.joinvl.getFeatures():
                # Allow user abort
                if self.abort is True:
                    break
                self.joinlind.insertFeature(feat)
#            self.status.emit('Join layer index created!')
            print 'Join layer index created!'
        # Does the join layer contain multi geometries?
        # Try to check the first feature
        # This is not used for anything yet
        self.joinmulti = False
        feats = self.joinvl.getFeatures()
        if feats is not None:
            testfeature = feats.next()
            feats.rewind()
            feats.close()
            if testfeature is not None:
                if testfeature.geometry() is not None:
                    if testfeature.geometry().isMultipart():
                        self.joinmulti = True
                else:
#                    self.status.emit('No join geometry!')
#                    self.finished.emit(False, None)
                    print 'No join geometry!'
                    return
            else:
#                self.status.emit('No join features!')
#                self.finished.emit(False, None)
                print 'No join features!'
                return

        #if feats.next().geometry().isMultipart():
        #    self.joinmulti = True
        #feats.rewind()
        #feats.close()

        # Prepare for the join by fetching the layers into memory
        # Add the input features to a list
        inputfeatures = self.inpvl.getFeatures()
        self.inputf = []
        for f in inputfeatures:
            self.inputf.append(f)
        # Add the join features to a list
        joinfeatures = self.joinvl.getFeatures()
        self.joinf = []
        for f in joinfeatures:
            self.joinf.append(f)
        self.features = []

        # Do the join!
        # Using the original features from the input layer
        for feat in self.inputf:
            # Allow user abort
            if self.abort is True:
                break
            self.do_indexjoin(feat)
            self.calculate_progress()
        self.mem_joinl.dataProvider().addFeatures(self.features)
#        self.status.emit('Join finished')
        print 'Join finished'
#        except:
#            import traceback
#            # self.error.emit(traceback.format_exc())
#            print traceback.format_exec()
#            self.finished.emit(False, None)
#            if self.mem_joinl is not None:
#                self.mem_joinl.rollBack()
#        else:
        self.mem_joinl.commitChanges()
        if self.abort:
            self.finished.emit(False, None)
        else:
#            self.status.emit('Delivering the memory layer...')
#            self.finished.emit(True, self.mem_joinl)
            print 'Delivering the memory layer...'
            QgsMapLayerRegistry.instance().addMapLayer(self.mem_joinl)

    def calculate_progress(self):
        '''Update progress and emit a signal with the percentage'''
        self.processed = self.processed + 1
        # update the progress bar at certain increments
        if (self.increment == 0 or
                self.processed % self.increment == 0):
            perc_new = (self.processed * 100) / self.feature_count
            if perc_new > self.percentage:
                self.percentage = perc_new
#                self.progress.emit(self.percentage)
                print self.percentage,

    def kill(self):
        '''Kill the thread by setting the abort flag'''
        self.abort = True

    def do_indexjoin(self, feat):
        '''Find the nearest neigbour using an index, if possible

        Parameter: feat -- The feature for which a neighbour is
                           sought
        '''
        infeature = feat
        infeatureid = infeature.id()
        inputgeom = QgsGeometry(infeature.geometry())
        # Shall approximate input geometries be used?
        if self.approximateinputgeom:
            # Use the centroid as the input geometry
            inputgeom = QgsGeometry(infeature.geometry()).centroid()
        # Check if the coordinate systems are equal, if not,
        # transform the input feature!
        if (self.inpvl.crs() != self.joinvl.crs()):
            try:
                inputgeom.transform(QgsCoordinateTransform(
                    self.inpvl.crs(), self.joinvl.crs()))
            except:
                import traceback
                self.error.emit(self.tr('CRS Transformation error!') +
                                ' - ' + traceback.format_exc())
                self.abort = True
                return
        nnfeature = None
        mindist = float("inf")
        ## Find the closest feature!
        if (self.approximateinputgeom or
                self.inpvl.wkbType() == QGis.WKBPoint or
                self.inpvl.wkbType() == QGis.WKBPoint25D):
            # The input layer's geometry type is point, or shall be
            # approximated to point (centroid).
            # Then a join index will always be used.
            if (self.usejoinlayerapprox or
                    self.joinvl.wkbType() == QGis.WKBPoint or
                    self.joinvl.wkbType() == QGis.WKBPoint25D):
                # The join layer's geometry type is point, or the
                # user wants approximate join geometries to be used.
                # Then the join index nearest neighbour function can
                # be used without refinement.
                if self.selfjoin:
                    # Self join!
                    # Have to get the two nearest neighbours
                    nearestids = self.joinlind.nearestNeighbor(
                                             inputgeom.asPoint(), 2)
                    if nearestids[0] == infeatureid and len(nearestids) > 1:
                        # The first feature is the same as the input
                        # feature, so choose the second one
                        nnfeature = self.joinvl.getFeatures(
                            QgsFeatureRequest(nearestids[1])).next()
                    else:
                        # The first feature is not the same as the
                        # input feature, so choose it
                        nnfeature = self.joinvl.getFeatures(
                            QgsFeatureRequest(nearestids[0])).next()
                    ## Pick the second closest neighbour!
                    ## (the first is supposed to be the point itself)
                    ## Should we check for coinciding points?
                    #nearestid = self.joinlind.nearestNeighbor(
                    #    inputgeom.asPoint(), 2)[1]
                    #nnfeature = self.joinvl.getFeatures(
                    #    QgsFeatureRequest(nearestid)).next()
                else:
                    # Not a self join, so we can search for only the
                    # nearest neighbour (1)
                    nearestid = self.joinlind.nearestNeighbor(
                                           inputgeom.asPoint(), 1)[0]
                    nnfeature = self.joinvl.getFeatures(
                                 QgsFeatureRequest(nearestid)).next()
                mindist = inputgeom.distance(nnfeature.geometry())
            elif (self.joinvl.wkbType() == QGis.WKBPolygon or
                  self.joinvl.wkbType() == QGis.WKBPolygon25D or
                  self.joinvl.wkbType() == QGis.WKBLineString or
                  self.joinvl.wkbType() == QGis.WKBLineString25D):
                # Use the join layer index to speed up the join when
                # the join layer geometry type is polygon or line
                # and the input layer geometry type is point or an
                # approximation (point)
                nearestindexid = self.joinlind.nearestNeighbor(
                    inputgeom.asPoint(), 1)[0]
                # Check for self join
                if self.selfjoin and nearestindexid == infeatureid:
                    # Self join and same feature, so get the two
                    # first two neighbours
                    nearestindexes = self.joinlind.nearestNeighbor(
                                             inputgeom.asPoint(), 2)
                    nearestindexid = nearestindexes[0]
                    if (nearestindexid == infeatureid and
                                  len(nearestindexes) > 1):
                        nearestindexid = nearestindexes[1]
                nnfeature = self.joinvl.getFeatures(
                    QgsFeatureRequest(nearestindexid)).next()
                mindist = inputgeom.distance(nnfeature.geometry())
                px = inputgeom.asPoint().x()
                py = inputgeom.asPoint().y()
                closefids = self.joinlind.intersects(QgsRectangle(
                    px - mindist,
                    py - mindist,
                    px + mindist,
                    py + mindist))
                for closefid in closefids:
                    if self.abort is True:
                        break
                    # Check for self join and same feature
                    if self.selfjoin and closefid == infeatureid:
                        continue
                    closef = self.joinvl.getFeatures(
                        QgsFeatureRequest(closefid)).next()
                    thisdistance = inputgeom.distance(closef.geometry())
                    if thisdistance < mindist:
                        mindist = thisdistance
                        nnfeature = closef
                    if mindist == 0:
                        break
            else:
                # Join with no index use
                # Go through all the features from the join layer!
                for inFeatJoin in self.joinf:
                    if self.abort is True:
                        break
                    joingeom = QgsGeometry(inFeatJoin.geometry())
                    thisdistance = inputgeom.distance(joingeom)
                    # If the distance is 0, check for equality of the
                    # features (in case it is a self join)
                    if (thisdistance == 0 and self.selfjoin and
                            infeatureid == inFeatJoin.id()):
                        continue
                    if thisdistance < mindist:
                        mindist = thisdistance
                        nnfeature = inFeatJoin
                    # For 0 distance, settle with the first feature
                    if mindist == 0:
                        break
        else:
            # non-simple point input geometries (could be multipoint)
            if (self.nonpointexactindex):
                # Use the spatial index on the join layer (default).
                # First we do an approximate search
                # Get the input geometry centroid
                centroid = QgsGeometry(infeature.geometry()).centroid()
                centroidgeom = centroid.asPoint()
                # Find the nearest neighbour (index geometries only)
                nearestid = self.joinlind.nearestNeighbor(centroidgeom, 1)[0]
                # Check for self join
                if self.selfjoin and nearestid == infeatureid:
                    # Self join and same feature, so get the two
                    # first two neighbours
                    nearestindexes = self.joinlind.nearestNeighbor(
                        centroidgeom, 2)
                    nearestid = nearestindexes[0]
                    if nearestid == infeatureid and len(nearestindexes) > 1:
                        nearestid = nearestindexes[1]
                nnfeature = self.joinvl.getFeatures(
                    QgsFeatureRequest(nearestid)).next()
                mindist = inputgeom.distance(nnfeature.geometry())
                # Calculate the search rectangle (inputgeom BBOX
                inpbbox = infeature.geometry().boundingBox()
                minx = inpbbox.xMinimum() - mindist
                maxx = inpbbox.xMaximum() + mindist
                miny = inpbbox.yMinimum() - mindist
                maxy = inpbbox.yMaximum() + mindist
                #minx = min(inpbbox.xMinimum(), centroidgeom.x() - mindist)
                #maxx = max(inpbbox.xMaximum(), centroidgeom.x() + mindist)
                #miny = min(inpbbox.yMinimum(), centroidgeom.y() - mindist)
                #maxy = max(inpbbox.yMaximum(), centroidgeom.y() + mindist)
                searchrectangle = QgsRectangle(minx, miny, maxx, maxy)
                # Fetch the candidate join geometries
                closefids = self.joinlind.intersects(searchrectangle)
                # Loop through the geometries and choose the closest
                # one
                for closefid in closefids:
                    if self.abort is True:
                        break
                    # Check for self join and identical feature
                    if self.selfjoin and closefid == infeatureid:
                        continue
                    closef = self.joinvl.getFeatures(
                        QgsFeatureRequest(closefid)).next()
                    thisdistance = inputgeom.distance(closef.geometry())
                    if thisdistance < mindist:
                        mindist = thisdistance
                        nnfeature = closef
                    if mindist == 0:
                        break
            else:
                # Join with no index use
                # Check all the features of the join layer!
                mindist = float("inf")  # should not be necessary
                for inFeatJoin in self.joinf:
                    if self.abort is True:
                        break
                    joingeom = QgsGeometry(inFeatJoin.geometry())
                    thisdistance = inputgeom.distance(joingeom)
                    # If the distance is 0, check for equality of the
                    # features (in case it is a self join)
                    if (thisdistance == 0 and self.selfjoin and
                            infeatureid == inFeatJoin.id()):
                        continue
                    if thisdistance < mindist:
                        mindist = thisdistance
                        nnfeature = inFeatJoin
                    # For 0 distance, settle with the first feature
                    if mindist == 0:
                        break
        if not self.abort:
            atMapA = infeature.attributes()
            atMapB = nnfeature.attributes()
            attrs = []
            attrs.extend(atMapA)
            attrs.extend(atMapB)
            attrs.append(mindist)

            outFeat = QgsFeature()
            # Use the original input layer geometry!:
            outFeat.setGeometry(QgsGeometry(infeature.geometry()))
            # Use the modified input layer geometry (could be
            # centroid)
            #outFeat.setGeometry(QgsGeometry(inputgeom))
            outFeat.setAttributes(attrs)
            self.calculate_progress()
            self.features.append(outFeat)
            #self.mem_joinl.dataProvider().addFeatures([outFeat])

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('NNJoinEngine', message)
