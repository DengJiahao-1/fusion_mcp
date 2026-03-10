"""
Sketch operations module.

Fusion 360 API operations for sketches.
"""

import adsk.core
import adsk.fusion
import math
import traceback
from typing import List, Optional

from .logger import get_default_logger

logger = get_default_logger()


def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise Exception("No active Fusion 360 document")
    return design


def _convert_mm_to_document_units(value_mm: float) -> float:
    try:
        design = _get_design()
        default_units = design.unitsManager.defaultLengthUnits
        if default_units == adsk.core.UnitsLength.MillimeterUnits:
            return value_mm
        if default_units == adsk.core.UnitsLength.CentimeterUnits:
            return value_mm / 10.0
        if default_units == adsk.core.UnitsLength.MeterUnits:
            return value_mm / 1000.0
        if default_units == adsk.core.UnitsLength.InchUnits:
            return value_mm / 25.4
        if default_units == adsk.core.UnitsLength.FootUnits:
            return value_mm / 304.8
        return value_mm
    except Exception:
        return value_mm


def _find_sketch_by_name(sketch_name: str) -> adsk.fusion.Sketch:
    if not sketch_name or not sketch_name.strip():
        raise Exception("sketch_name is required")
    design = _get_design()
    root_comp = design.rootComponent
    for sk in root_comp.sketches:
        if sk.name == sketch_name:
            return sk
    raise Exception(f"Sketch not found: {sketch_name}")


def create_sketch(plane: str = "XY", name: Optional[str] = None) -> str:
    """Create new sketch. plane: XY/XZ/YZ/Top/Front/Right. name: optional."""
    try:
        app = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app.activeProduct)
        
        if not design:
            raise Exception("No active Fusion 360 document")
        
        rootComp = design.rootComponent
        
        # Get sketch plane
        sketch_plane = _get_sketch_plane(rootComp, plane)
        if not sketch_plane:
            raise Exception(f"Plane not found: {plane}")
        
        # Create sketch
        sketches = rootComp.sketches
        sketch = sketches.add(sketch_plane)
        
        # Set sketch name
        if name:
            sketch.name = name
        
        return f"Sketch '{sketch.name}' created"
    
    except Exception as e:
        error_msg = f"Create sketch failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def create_sketch_offset(plane: str, offset: float, name: Optional[str] = None) -> str:
    """
    Create a sketch on an offset construction plane.
    """
    try:
        design = _get_design()
        root_comp = design.rootComponent

        base_plane = _get_sketch_plane(root_comp, plane)
        if not base_plane:
            raise Exception(f"Plane not found: {plane}")

        offset_value = _convert_mm_to_document_units(offset)
        planes = root_comp.constructionPlanes
        plane_input = planes.createInput()
        plane_input.setByOffset(base_plane, adsk.core.ValueInput.createByReal(offset_value))
        offset_plane = planes.add(plane_input)

        sketch = root_comp.sketches.add(offset_plane)
        if name:
            sketch.name = name

        return f"Offset sketch '{sketch.name}' created"
    except Exception as e:
        error_msg = f"Create offset sketch failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def delete_sketch(sketch_name: str) -> str:
    """Delete sketch by name."""
    try:
        app = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app.activeProduct)
        
        if not design:
            raise Exception("No active Fusion 360 document")
        
        rootComp = design.rootComponent
        
        # Find sketch to delete
        sketch = None
        for s in rootComp.sketches:
            if s.name == sketch_name:
                sketch = s
                break
        
        if not sketch:
            raise Exception(f"Sketch '{sketch_name}' not found")
        
        # Delete sketch
        sketch.deleteMe()
        
        return f"Sketch '{sketch_name}' deleted"
    
    except Exception as e:
        error_msg = f"Delete sketch failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def _get_sketch_plane(rootComp: adsk.fusion.Component, plane_name: str) -> Optional[adsk.core.Base]:
    """
    Get sketch plane. rootComp: root component. plane_name: XY/XZ/YZ/Top/Front/Right.
    """
    plane_name_upper = plane_name.upper()
    
    if plane_name_upper == "XY" or plane_name.lower() == "top":
        # XY (top)
        return rootComp.xYConstructionPlane
    
    elif plane_name_upper == "XZ" or plane_name.lower() == "front":
        # XZ (front)
        return rootComp.xZConstructionPlane
    
    elif plane_name_upper == "YZ" or plane_name.lower() == "right":
        # YZ (right)
        return rootComp.yZConstructionPlane
    
    else:
        return None


def add_line(sketch_name: str, x1: float, y1: float, x2: float, y2: float) -> str:
    try:
        sketch = _find_sketch_by_name(sketch_name)
        x1 = _convert_mm_to_document_units(x1)
        y1 = _convert_mm_to_document_units(y1)
        x2 = _convert_mm_to_document_units(x2)
        y2 = _convert_mm_to_document_units(y2)

        p1 = adsk.core.Point3D.create(x1, y1, 0.0)
        p2 = adsk.core.Point3D.create(x2, y2, 0.0)
        sketch.sketchCurves.sketchLines.addByTwoPoints(p1, p2)
        return f"Line added to sketch '{sketch_name}'"
    except Exception as e:
        error_msg = f"Add line failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def add_rectangle_by_center(
    sketch_name: str,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
) -> str:
    try:
        sketch = _find_sketch_by_name(sketch_name)
        center_x = _convert_mm_to_document_units(center_x)
        center_y = _convert_mm_to_document_units(center_y)
        width = _convert_mm_to_document_units(width)
        height = _convert_mm_to_document_units(height)

        x0 = center_x - width / 2
        y0 = center_y - height / 2

        p1 = adsk.core.Point3D.create(x0, y0, 0.0)
        p2 = adsk.core.Point3D.create(x0 + width, y0, 0.0)
        p3 = adsk.core.Point3D.create(x0 + width, y0 + height, 0.0)
        p4 = adsk.core.Point3D.create(x0, y0 + height, 0.0)

        lines = sketch.sketchCurves.sketchLines
        lines.addByTwoPoints(p1, p2)
        lines.addByTwoPoints(p2, p3)
        lines.addByTwoPoints(p3, p4)
        lines.addByTwoPoints(p4, p1)
        return f"Rectangle added to sketch '{sketch_name}'"
    except Exception as e:
        error_msg = f"Add rectangle failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def add_rectangle_by_corners(
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> str:
    try:
        sketch = _find_sketch_by_name(sketch_name)
        x1 = _convert_mm_to_document_units(x1)
        y1 = _convert_mm_to_document_units(y1)
        x2 = _convert_mm_to_document_units(x2)
        y2 = _convert_mm_to_document_units(y2)

        p1 = adsk.core.Point3D.create(x1, y1, 0.0)
        p2 = adsk.core.Point3D.create(x2, y1, 0.0)
        p3 = adsk.core.Point3D.create(x2, y2, 0.0)
        p4 = adsk.core.Point3D.create(x1, y2, 0.0)

        lines = sketch.sketchCurves.sketchLines
        lines.addByTwoPoints(p1, p2)
        lines.addByTwoPoints(p2, p3)
        lines.addByTwoPoints(p3, p4)
        lines.addByTwoPoints(p4, p1)
        return f"Rectangle added to sketch '{sketch_name}'"
    except Exception as e:
        error_msg = f"Add rectangle failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def add_circle(sketch_name: str, center_x: float, center_y: float, radius: float) -> str:
    try:
        sketch = _find_sketch_by_name(sketch_name)
        center_x = _convert_mm_to_document_units(center_x)
        center_y = _convert_mm_to_document_units(center_y)
        radius = _convert_mm_to_document_units(radius)

        center = adsk.core.Point3D.create(center_x, center_y, 0.0)
        sketch.sketchCurves.sketchCircles.addByCenterRadius(center, radius)
        return f"Circle added to sketch '{sketch_name}'"
    except Exception as e:
        error_msg = f"Add circle failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def add_arc_3pt(
    sketch_name: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x3: float,
    y3: float,
) -> str:
    try:
        sketch = _find_sketch_by_name(sketch_name)
        x1 = _convert_mm_to_document_units(x1)
        y1 = _convert_mm_to_document_units(y1)
        x2 = _convert_mm_to_document_units(x2)
        y2 = _convert_mm_to_document_units(y2)
        x3 = _convert_mm_to_document_units(x3)
        y3 = _convert_mm_to_document_units(y3)

        p1 = adsk.core.Point3D.create(x1, y1, 0.0)
        p2 = adsk.core.Point3D.create(x2, y2, 0.0)
        p3 = adsk.core.Point3D.create(x3, y3, 0.0)
        sketch.sketchCurves.sketchArcs.addByThreePoints(p1, p2, p3)
        return f"Arc added to sketch '{sketch_name}'"
    except Exception as e:
        error_msg = f"Add arc failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def add_polyline(sketch_name: str, points: List[List[float]]) -> str:
    try:
        if not points or len(points) < 2:
            raise Exception("At least two points are required")
        # If first!=last, auto-close by appending first point
        pts = [p[:2] for p in points if len(p) >= 2]
        if len(pts) >= 3:
            x0, y0 = float(pts[0][0]), float(pts[0][1])
            xn, yn = float(pts[-1][0]), float(pts[-1][1])
            if abs(x0 - xn) > 1e-9 or abs(y0 - yn) > 1e-9:
                pts.append([x0, y0])
        sketch = _find_sketch_by_name(sketch_name)
        lines = sketch.sketchCurves.sketchLines
        last_point = None
        for pt in pts:
            x = _convert_mm_to_document_units(pt[0])
            y = _convert_mm_to_document_units(pt[1])
            p = adsk.core.Point3D.create(x, y, 0.0)
            if last_point is not None:
                lines.addByTwoPoints(last_point, p)
            last_point = p
        return f"Polyline added to sketch '{sketch_name}'"
    except Exception as e:
        error_msg = f"Add polyline failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def create_helix_sketch(
    name: Optional[str],
    center_x: float,
    center_y: float,
    center_z: float,
    radius: float,
    height: float,
    turns: float,
    points_per_turn: int = 32,
) -> str:
    try:
        if turns <= 0 or points_per_turn < 4:
            raise Exception("Invalid helix parameters")

        design = _get_design()
        root_comp = design.rootComponent
        sketch = root_comp.sketches.add(root_comp.xYConstructionPlane)
        sketch.is3D = True
        if name:
            sketch.name = name

        cx = _convert_mm_to_document_units(center_x)
        cy = _convert_mm_to_document_units(center_y)
        cz = _convert_mm_to_document_units(center_z)
        r = _convert_mm_to_document_units(radius)
        h = _convert_mm_to_document_units(height)

        total_points = max(int(turns * points_per_turn) + 1, 2)
        points_collection = adsk.core.ObjectCollection.create()
        for i in range(total_points):
            t = i / (total_points - 1)
            angle = 2.0 * 3.141592653589793 * turns * t
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            z = cz + h * t
            points_collection.add(adsk.core.Point3D.create(x, y, z))

        sketch.sketchCurves.sketchFittedSplines.add(points_collection)
        return f"Helix sketch '{sketch.name}' created"
    except Exception as e:
        error_msg = f"Create helix sketch failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)

