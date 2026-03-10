"""
Feature operations module.

Fusion 360 API for features (box, cylinder, extrude, etc.).
"""

import re

import adsk.core
import adsk.fusion
import math
import traceback
from typing import Dict, Iterable, List, Optional

from .logger import get_default_logger

logger = get_default_logger()
def _get_design() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise Exception("No active Fusion 360 document")
    return design


def _get_root_component() -> adsk.fusion.Component:
    return _get_design().rootComponent


def _get_feature_operation(operation: Optional[str]) -> adsk.fusion.FeatureOperations:
    mapping = {
        None: adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        "NewBody": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
        "Join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "Merge": adsk.fusion.FeatureOperations.JoinFeatureOperation,  # Merge is alias for Join
        "Cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
        "Intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation,
        "NewComponent": adsk.fusion.FeatureOperations.NewComponentFeatureOperation,
    }
    op = mapping.get(operation)
    if op is None:
        raise Exception(f"Unsupported feature operation: {operation}")
    return op


def _find_sketch(root_comp: adsk.fusion.Component, sketch_name: str) -> adsk.fusion.Sketch:
    for sketch in root_comp.sketches:
        if sketch.name == sketch_name:
            return sketch
    raise Exception(f"Sketch '{sketch_name}' not found")


def _find_profile(root_comp: adsk.fusion.Component, profile_name: str) -> adsk.fusion.Profile:
    sketch = _find_sketch(root_comp, profile_name)
    profiles = sketch.profiles
    if profiles.count == 0:
        raise Exception(f"Sketch '{profile_name}' has no closed profile")
    return profiles.item(0)


def _find_body(root_comp: adsk.fusion.Component, body_name: str) -> adsk.fusion.BRepBody:
    """
    Find body by name, with exact and fuzzy matching.
    
    Args:
        root_comp: Root component
        body_name: Body name (exact or partial match)
    
    Returns:
        The matching body
    
    Raises:
        Exception: If no matching body is found
    """
    if not body_name or not body_name.strip():
        raise Exception("Body name cannot be empty")
    
    body_name = body_name.strip()
    
    # Try exact match first
    for body in root_comp.bRepBodies:
        if body.name == body_name:
            return body
    
    # If exact match fails, try partial (containment) match
    matching_bodies = []
    for body in root_comp.bRepBodies:
        body_name_actual = body.name or ""
        # Check containment (case-insensitive)
        if body_name.lower() in body_name_actual.lower() or body_name_actual.lower() in body_name.lower():
            matching_bodies.append((body, body_name_actual))
    
    if len(matching_bodies) == 1:
        # Single match, return it
        return matching_bodies[0][0]
    elif len(matching_bodies) > 1:
        # Multiple matches, list all
        names = [name for _, name in matching_bodies]
        raise Exception(
            f"Multiple bodies match '{body_name}': {', '.join(names)}. "
            f"Use get_document_content for exact names."
        )
    else:
        # BodyN or entity N mapping (Body1 = first body by index)
        ent_match = re.match(r"^Body\s*(\d+)\s*$", body_name.strip(), re.IGNORECASE)
        if ent_match:
            idx = int(ent_match.group(1))
            if 1 <= idx <= root_comp.bRepBodies.count:
                return root_comp.bRepBodies.item(idx - 1)
        # If doc has only one body, treat as user referring to it
        body_count = root_comp.bRepBodies.count
        if body_count == 1:
            return root_comp.bRepBodies.item(0)
        all_names = [body.name or f"Body{i}" for i, body in enumerate(root_comp.bRepBodies)]
        if all_names:
            raise Exception(
                f"Body '{body_name}' not found. "
                f"Available body names: {', '.join(all_names)}. "
                f"Use get_document_content for exact names."
            )
        else:
            raise Exception(f"Body '{body_name}' not found. Document has no bodies.")


def _collect_edges(body: adsk.fusion.BRepBody, edge_indices: Optional[Iterable[int]]) -> adsk.core.ObjectCollection:
    collection = adsk.core.ObjectCollection.create()
    if edge_indices:
        for idx in edge_indices:
            try:
                collection.add(body.edges.item(int(idx)))
            except Exception:
                raise Exception(f"Body '{body.name}' has no edge at index {idx}")
    else:
        for i in range(body.edges.count):
            collection.add(body.edges.item(i))
    if collection.count == 0:
        raise Exception("No edges available for operation")
    return collection


def _collect_faces(body: adsk.fusion.BRepBody, face_indices: Optional[Iterable[int]]) -> adsk.core.ObjectCollection:
    collection = adsk.core.ObjectCollection.create()
    if not face_indices:
        return collection
    for idx in face_indices:
        try:
            collection.add(body.faces.item(int(idx)))
        except Exception:
            raise Exception(f"Body '{body.name}' has no face at index {idx}")
    return collection


def _get_axis(root_comp: adsk.fusion.Component, axis: str) -> adsk.fusion.ConstructionAxis:
    axis = (axis or "Z").upper()
    if axis == "X":
        return root_comp.xConstructionAxis
    if axis == "Y":
        return root_comp.yConstructionAxis
    if axis == "Z":
        return root_comp.zConstructionAxis
    raise Exception(f"Unsupported axis: {axis}")


def _convert_mm_to_document_units(value_mm: float) -> float:
    """
    Convert millimeter to document default length units.
    
    Args:
        value_mm: Value in millimeters
    
    Returns:
        Value in document default units
    """
    try:
        design = _get_design()
        default_units = design.unitsManager.defaultLengthUnits
        
        # Already in mm, return as-is
        if default_units == adsk.core.UnitsLength.MillimeterUnits:
            return value_mm
        
        # Convert to document units
        if default_units == adsk.core.UnitsLength.CentimeterUnits:
            return value_mm / 10.0  # mm to cm
        elif default_units == adsk.core.UnitsLength.MeterUnits:
            return value_mm / 1000.0  # mm to m
        elif default_units == adsk.core.UnitsLength.InchUnits:
            return value_mm / 25.4  # mm to inch
        elif default_units == adsk.core.UnitsLength.FootUnits:
            return value_mm / 304.8  # mm to foot
        else:
            return value_mm  # Fallback: assume mm
    except Exception:
        return value_mm  # On failure, return original


def _convert_document_units_to_mm(value_doc: float) -> float:
    """
    Convert document default units to millimeters.
    
    Args:
        value_doc: Value in document default units
    
    Returns:
        Value in millimeters
    """
    try:
        design = _get_design()
        default_units = design.unitsManager.defaultLengthUnits
        
        # Already in mm, return as-is
        if default_units == adsk.core.UnitsLength.MillimeterUnits:
            return value_doc
        
        # Convert to millimeters
        if default_units == adsk.core.UnitsLength.CentimeterUnits:
            return value_doc * 10.0  # cm to mm
        elif default_units == adsk.core.UnitsLength.MeterUnits:
            return value_doc * 1000.0  # m to mm
        elif default_units == adsk.core.UnitsLength.InchUnits:
            return value_doc * 25.4  # inch to mm
        elif default_units == adsk.core.UnitsLength.FootUnits:
            return value_doc * 304.8  # foot to mm
        else:
            return value_doc  # Fallback: assume mm
    except Exception:
        return value_doc  # On failure, return original


def _name_edges(body: adsk.fusion.BRepBody, 
                edge_name_map: Optional[Dict[str, str]] = None,
                entity_type: Optional[str] = None,
                entity_params: Optional[Dict[str, float]] = None) -> None:
    """
    Name all edges of a body.
    
    Args:
        body: Body to name edges for
        edge_name_map: Optional mapping e.g. {"length": "a", "width": "b", "height": "h"}
            If provided, uses direction-based prefix
        entity_type: Entity type ("box", "cylinder", "sphere") for naming strategy
        entity_params: Entity params (width, height, depth) to identify edge direction
    """
    try:
        body_name = body.name or "Body"
        edges_count = body.edges.count
        
        # If custom mapping provided, name by edge direction
        if edge_name_map and entity_type == "box" and entity_params:
            _name_box_edges_by_direction(body, edge_name_map, entity_params)
            return
        
        # Default naming: {body_name}_edge_{index}
        for i in range(edges_count):
            try:
                edge = body.edges.item(i)
                edge_name = f"{body_name}_edge_{i}"
                edge.name = edge_name
            except Exception:
                # If edge naming fails, continue to next
                pass
    except Exception:
        # If naming fails, do not affect body creation (silent)
        pass


def _name_box_edges_by_direction(body: adsk.fusion.BRepBody, 
                                  edge_name_map: Dict[str, str],
                                  entity_params: Dict[str, float]) -> None:
    """
    Name box edges by direction.
    
    Args:
        body: Box body
        edge_name_map: Mapping e.g. {"length": "a", "width": "b", "height": "h"}
        entity_params: Entity params (width, height, depth)
    """
    try:
        # Get naming prefixes
        length_name = edge_name_map.get("length", "length")
        width_name = edge_name_map.get("width", "width")
        height_name = edge_name_map.get("height", "height")
        
        # Get body dimensions (for edge direction)
        width = entity_params.get("width", 0)
        height = entity_params.get("height", 0)
        depth = entity_params.get("depth", 0)
        
        # Counters for edges in same direction
        length_count = 0
        width_count = 0
        height_count = 0
        
        edges_count = body.edges.count
        
        for i in range(edges_count):
            try:
                edge = body.edges.item(i)
                
                # Get edge geometry
                edge_geom = edge.geometry
                if not edge_geom:
                    # Fallback to default if no geometry
                    edge.name = f"{body.name or 'Body'}_edge_{i}"
                    continue
                
                # Try to get edge start and end points
                # For straight edges, use vertices
                try:
                    # Get edge vertices
                    vertices = edge.vertices
                    if vertices.count < 2:
                        # If not enough vertices, try geometry
                        if hasattr(edge_geom, 'startPoint') and hasattr(edge_geom, 'endPoint'):
                            start_point = edge_geom.startPoint
                            end_point = edge_geom.endPoint
                        else:
                            edge.name = f"{body.name or 'Body'}_edge_{i}"
                            continue
                    else:
                        start_point = vertices.item(0).geometry
                        end_point = vertices.item(vertices.count - 1).geometry
                except Exception:
                    # If no vertices, try geometry
                    try:
                        if hasattr(edge_geom, 'startPoint') and hasattr(edge_geom, 'endPoint'):
                            start_point = edge_geom.startPoint
                            end_point = edge_geom.endPoint
                        else:
                            edge.name = f"{body.name or 'Body'}_edge_{i}"
                            continue
                    except Exception:
                        edge.name = f"{body.name or 'Body'}_edge_{i}"
                        continue
                
                # Compute edge direction vector
                direction = adsk.core.Vector3D.create(
                    end_point.x - start_point.x,
                    end_point.y - start_point.y,
                    end_point.z - start_point.z
                )
                
                # Normalize direction vector
                length_vec = direction.length
                if length_vec < 1e-9:
                    edge.name = f"{body.name or 'Body'}_edge_{i}"
                    continue
                
                direction.normalize()
                
                # Determine main direction (X, Y, or Z)
                abs_x = abs(direction.x)
                abs_y = abs(direction.y)
                abs_z = abs(direction.z)
                
                # Determine main edge direction
                if abs_x > abs_y and abs_x > abs_z:
                    # Mainly along X (length)
                    edge_name = f"{length_name}_edge_{length_count}"
                    length_count += 1
                elif abs_y > abs_x and abs_y > abs_z:
                    # Mainly along Y (width)
                    edge_name = f"{width_name}_edge_{width_count}"
                    width_count += 1
                elif abs_z > abs_x and abs_z > abs_y:
                    # Mainly along Z (height)
                    edge_name = f"{height_name}_edge_{height_count}"
                    height_count += 1
                else:
                    # Unknown direction, use default naming
                    edge_name = f"{body.name or 'Body'}_edge_{i}"
                
                edge.name = edge_name
            except Exception:
                # If edge naming fails, use default
                try:
                    edge.name = f"{body.name or 'Body'}_edge_{i}"
                except Exception:
                    pass
    except Exception:
        # If naming fails, fallback to default
        try:
            for i in range(body.edges.count):
                try:
                    edge = body.edges.item(i)
                    edge.name = f"{body.name or 'Body'}_edge_{i}"
                except Exception:
                    pass
        except Exception:
            pass




def create_box(width: float, height: float, depth: float, 
               center_x: float = 0.0, center_y: float = 0.0, center_z: float = 0.0,
               edge_names: Optional[Dict[str, str]] = None,
               name: Optional[str] = None) -> str:
    """
    Create box feature
    
    Creates box via sketch and extrude at given coordinates.
    
    Args:
        width: Width (X, mm)
        height: Height (Y, mm)
        depth: Depth (Z, mm)
        center_x: Center X (mm)
        center_y: Center Y (mm)
        center_z: Center Z (mm)
        edge_names: Optional edge naming map.
            Format: {"length": "a", "width": "b", "height": "h"}
            - "length": Prefix for X-direction edges (e.g. "a")
            - "width": Prefix for Y-direction edges (e.g. "b")
            - "height": Prefix for Z-direction edges (e.g. "h")
            If not provided, default: {body_name}_edge_{index}
    
    Returns:
        Result message
    """
    try:
        # Convert input mm to document units
        width = _convert_mm_to_document_units(width)
        height = _convert_mm_to_document_units(height)
        depth = _convert_mm_to_document_units(depth)
        center_x = _convert_mm_to_document_units(center_x)
        center_y = _convert_mm_to_document_units(center_y)
        center_z = _convert_mm_to_document_units(center_z)
        
        rootComp = _get_root_component()
        
        # Get XY plane
        xy_plane = rootComp.xYConstructionPlane
        
        # Create sketch
        sketches = rootComp.sketches
        sketch = sketches.add(xy_plane)
        
        # Draw rectangle on XY plane (Z=0)
        # Offset rect center to target position
        rect_x = center_x - width / 2
        rect_y = center_y - height / 2
        
        # Create rect points (sketch on XY, Z=0)
        point1 = adsk.core.Point3D.create(rect_x, rect_y, 0.0)
        point2 = adsk.core.Point3D.create(rect_x + width, rect_y, 0.0)
        point3 = adsk.core.Point3D.create(rect_x + width, rect_y + height, 0.0)
        point4 = adsk.core.Point3D.create(rect_x, rect_y + height, 0.0)
        
        # Draw rect lines
        lines = sketch.sketchCurves.sketchLines
        lines.addByTwoPoints(point1, point2)
        lines.addByTwoPoints(point2, point3)
        lines.addByTwoPoints(point3, point4)
        lines.addByTwoPoints(point4, point1)
        
        # Get profile
        profiles = sketch.profiles
        if profiles.count == 0:
            raise Exception("Cannot create rectangular profile")
        
        profile = profiles.item(0)
        
        # Create extrude feature
        features = rootComp.features
        extrude_features = features.extrudeFeatures
        
        # Create extrude input
        extrude_input = extrude_features.createInput(
            profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        
        # Set extrude distance (setDistanceExtent(isSymmetric, distance))
        distance_input = adsk.core.ValueInput.createByReal(abs(depth))
        extrude_input.setDistanceExtent(False, distance_input)
        
        # Create extrude feature
        extrude_feature = extrude_features.add(extrude_input)
        
        # Check extrude success
        if not extrude_feature:
            raise Exception("Extrude feature creation failed")
        
        # Get created body
        if extrude_feature.bodies.count == 0:
            raise Exception("No body created after extrude")
        
        body = extrude_feature.bodies.item(0)
        
        # Name body edges
        entity_params = {
            "width": width,
            "height": height,
            "depth": depth
        }
        _name_edges(body, edge_name_map=edge_names, entity_type="box", entity_params=entity_params)
        
        # Compute move distance: body center at (center_x, center_y, depth/2) -> (center_x, center_y, center_z)
        move_x = 0.0
        move_y = 0.0
        move_z = center_z - depth / 2
        
        # If center not at origin, move body
        if abs(move_x) > 1e-9 or abs(move_y) > 1e-9 or abs(move_z) > 1e-9:
            # Move body to target position
            move_features = features.moveFeatures
            
            # Create body collection
            bodies_collection = adsk.core.ObjectCollection.create()
            bodies_collection.add(body)
            
            # Create transform matrix
            transform = adsk.core.Matrix3D.create()
            transform.translation = adsk.core.Vector3D.create(move_x, move_y, move_z)
            
            # Create move input (first param: ObjectCollection)
            move_feature_input = move_features.createInput(
                bodies_collection,
                transform
            )
            
            # Execute move
            move_feature = move_features.add(move_feature_input)
            
            # Check move success
            if not move_feature:
                raise Exception(f"Move body failed, vector: ({move_x}, {move_y}, {move_z})")
        
        # If name given, set body name (for modify_body_dimensions consistency)
        if name:
            body.name = name
        result_name = body.name or "Body"
        
        return f"Box created: width {_convert_document_units_to_mm(width)}mm (X), height {_convert_document_units_to_mm(height)}mm (Y), depth {_convert_document_units_to_mm(depth)}mm (Z). Entity name: '{result_name}'"
    
    except Exception as e:
        error_msg = f"Create box failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def create_entity_relative(
    entity_type: str,
    base_body_name: Optional[str] = None,
    direction: str = "above",
    distance: float = 0.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    # Box params
    width: Optional[float] = None,
    height: Optional[float] = None,
    depth: Optional[float] = None,
    # Cylinder params
    radius: Optional[float] = None,
    cylinder_height: Optional[float] = None,
    cylinder_axis: str = "Z",
) -> str:
    """
    Create new body (box or cylinder) relative to a base body.
    
    Uses base body bounding box to compute new body position.
    
    Args:
        entity_type: "box" or "cylinder"
        base_body_name: Base body name (optional); if omitted, uses last body
        direction: Relative to base body:
            "above"/"top"/"+Z": above (Z+), "below"/"bottom"/"-Z": below (Z-),
            "front"/"+Y": front (Y+), "back"/"-Y": back (Y-),
            "right"/"+X": right (X+), "left"/"-X": left (X-)
        distance: Gap between bodies (mm)
        offset_x/y/z: Center offset from base center (mm)
        
        Box params (when entity_type="box"): width, height, depth (X,Y,Z size)
        Cylinder params: radius, cylinder_height, cylinder_axis ("X","Y","Z", default "Z")
    
    Returns:
        Result message
    """
    try:
        rootComp = _get_root_component()
        
        # Get base body
        base_body = None
        if base_body_name:
            base_body = _find_body(rootComp, base_body_name)
        else:
            # If no body name given, use last body
            if rootComp.bRepBodies.count == 0:
                raise Exception("No bodies in document, cannot create relative entity")
            base_body = rootComp.bRepBodies.item(rootComp.bRepBodies.count - 1)
            base_body_name = base_body.name or "last body"
        
        # Get base body bounding box
        bbox = base_body.boundingBox
        if not bbox:
            raise Exception(f"Cannot get bounding box for body '{base_body_name}'")
        
        # Compute base center and bounds (doc units)
        base_center_x_doc = (bbox.minPoint.x + bbox.maxPoint.x) / 2
        base_center_y_doc = (bbox.minPoint.y + bbox.maxPoint.y) / 2
        base_center_z_doc = (bbox.minPoint.z + bbox.maxPoint.z) / 2
        
        # Convert input mm to doc units
        distance = _convert_mm_to_document_units(distance)
        offset_x = _convert_mm_to_document_units(offset_x)
        offset_y = _convert_mm_to_document_units(offset_y)
        offset_z = _convert_mm_to_document_units(offset_z)
        
        # Normalize direction
        direction_lower = direction.lower()
        direction_map = {
            "above": "+Z", "top": "+Z", "+z": "+Z",
            "below": "-Z", "bottom": "-Z", "-z": "-Z",
            "front": "+Y", "+y": "+Y",
            "back": "-Y", "-y": "-Y",
            "right": "+X", "+x": "+X",
            "left": "-X", "-x": "-X",
        }
        normalized_direction = direction_map.get(direction_lower, direction_lower)
        
        # Convert size params to doc units
        width_doc = _convert_mm_to_document_units(width) if width is not None else None
        height_doc = _convert_mm_to_document_units(height) if height is not None else None
        depth_doc = _convert_mm_to_document_units(depth) if depth is not None else None
        radius_doc = _convert_mm_to_document_units(radius) if radius is not None else None
        cylinder_height_doc = _convert_mm_to_document_units(cylinder_height) if cylinder_height is not None else None
        
        # Init new body center (align with base, then adjust)
        new_center_x = base_center_x_doc
        new_center_y = base_center_y_doc
        new_center_z = base_center_z_doc
        
        # Compute position by direction (doc units)
        # Use top-face alignment for above
        # Matches intuitive above semantics
        if normalized_direction == "+Z":  # Above
            entity_size = depth_doc if entity_type == "box" else cylinder_height_doc
            if entity_size is None:
                raise Exception("Box requires depth; cylinder requires cylinder_height")
            
            # Base top surface (Z max)
            base_top_z = bbox.maxPoint.z
            
            # New center = base top + distance + half height
            # distance=0: surfaces touch
            # distance>0: gap between surfaces
            # distance = surface-to-surface, not center-to-center
            new_center_z = base_top_z + distance + (entity_size / 2)
            
            # X,Y: align with base center + offset
            new_center_x = base_center_x_doc + offset_x
            new_center_y = base_center_y_doc + offset_y
            # Z offset: additional to computed Z
            new_center_z = new_center_z + offset_z
        elif normalized_direction == "-Z":  # Below
            entity_size = depth_doc if entity_type == "box" else cylinder_height_doc
            if entity_size is None:
                raise Exception("Box requires depth; cylinder requires cylinder_height")
            
            # Base bottom surface (Z min)
            base_bottom_z = bbox.minPoint.z
            
            # New center = base bottom - distance - half height
            # distance=0: surfaces touch
            # distance>0: gap between surfaces
            # distance = surface-to-surface, not center-to-center
            new_center_z = base_bottom_z - distance - (entity_size / 2)
            
            # X,Y: align with base center + offset
            new_center_x = base_center_x_doc + offset_x
            new_center_y = base_center_y_doc + offset_y
            # Z offset: additional to computed Z
            new_center_z = new_center_z + offset_z
        elif normalized_direction == "+Y":  # Front
            entity_size = height_doc if entity_type == "box" else (cylinder_height_doc if cylinder_axis == "Y" else radius_doc * 2 if radius_doc is not None else None)
            if entity_size is None:
                raise Exception("Box requires height; cylinder requires radius or cylinder_height")
            
            # Base front surface (Y max)
            base_front_y = bbox.maxPoint.y
            
            # New center = base front + distance + half size
            # distance=0: surfaces touch
            # distance>0: gap
            new_center_y = base_front_y + distance + (entity_size / 2)
            
            # X,Z: align with base + offset
            new_center_x = base_center_x_doc + offset_x
            new_center_z = base_center_z_doc + offset_z
            # Y offset: additional
            new_center_y = new_center_y + offset_y
        elif normalized_direction == "-Y":  # Back
            entity_size = height_doc if entity_type == "box" else (cylinder_height_doc if cylinder_axis == "Y" else radius_doc * 2 if radius_doc is not None else None)
            if entity_size is None:
                raise Exception("Box requires height; cylinder requires radius or cylinder_height")
            
            # Base back surface (Y min)
            base_back_y = bbox.minPoint.y
            
            # New center = base back - distance - half size
            # distance=0: surfaces touch
            # distance>0: gap
            new_center_y = base_back_y - distance - (entity_size / 2)
            
            # X,Z: align with base + offset
            new_center_x = base_center_x_doc + offset_x
            new_center_z = base_center_z_doc + offset_z
            # Y offset: additional
            new_center_y = new_center_y + offset_y
        elif normalized_direction == "+X":  # Right
            entity_size = width_doc if entity_type == "box" else (cylinder_height_doc if cylinder_axis == "X" else radius_doc * 2 if radius_doc is not None else None)
            if entity_size is None:
                raise Exception("Box requires width; cylinder requires radius or cylinder_height")
            
            # Base right surface (X max)
            base_right_x = bbox.maxPoint.x
            
            # New center = base right + distance + half size
            # distance=0: surfaces touch
            # distance>0: gap
            new_center_x = base_right_x + distance + (entity_size / 2)
            
            # Y,Z: align with base + offset
            new_center_y = base_center_y_doc + offset_y
            new_center_z = base_center_z_doc + offset_z
            # X offset: additional
            new_center_x = new_center_x + offset_x
        elif normalized_direction == "-X":  # Left
            entity_size = width_doc if entity_type == "box" else (cylinder_height_doc if cylinder_axis == "X" else radius_doc * 2 if radius_doc is not None else None)
            if entity_size is None:
                raise Exception("Box requires width; cylinder requires radius or cylinder_height")
            
            # Base left surface (X min)
            base_left_x = bbox.minPoint.x
            
            # New center = base left - distance - half size
            # distance=0: surfaces touch
            # distance>0: gap
            new_center_x = base_left_x - distance - (entity_size / 2)
            
            # Y,Z: align with base + offset
            new_center_y = base_center_y_doc + offset_y
            new_center_z = base_center_z_doc + offset_z
            # X offset: additional
            new_center_x = new_center_x + offset_x
        else:
            raise Exception(f"Unsupported direction: {direction}. Use: above/below/front/back/right/left")
        
        # Convert doc coords back to mm (create_box/cylinder expect mm)
        new_center_x_mm = _convert_document_units_to_mm(new_center_x)
        new_center_y_mm = _convert_document_units_to_mm(new_center_y)
        new_center_z_mm = _convert_document_units_to_mm(new_center_z)
        
        # Create by entity type (mm params, converted internally)
        if entity_type.lower() == "box":
            if width is None or height is None or depth is None:
                raise Exception("Box requires width, height and depth")
            return create_box(
                width=width,
                height=height,
                depth=depth,
                center_x=new_center_x_mm,
                center_y=new_center_y_mm,
                center_z=new_center_z_mm
            )
        elif entity_type.lower() == "cylinder":
            if radius is None or cylinder_height is None:
                raise Exception("Cylinder requires radius and cylinder_height")
            return create_cylinder(
                radius=radius,
                height=cylinder_height,
                center_x=new_center_x_mm,
                center_y=new_center_y_mm,
                center_z=new_center_z_mm,
                axis=cylinder_axis
            )
        else:
            raise Exception(f"Unsupported entity_type: {entity_type}, use box or cylinder")
    
    except Exception as e:
        error_msg = f"Create entity relative failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def create_cylinder(radius: float, height: float,
                   center_x: float = 0.0, center_y: float = 0.0, center_z: float = 0.0,
                   axis: str = "Z",
                   name: Optional[str] = None) -> str:
    """
    Create cylinder feature
    
    Creates cylinder via circular sketch and extrude.
    
    Args:
        radius: Radius (mm)
        height: Height (mm)
        center_x: Center X (mm)
        center_y: Center Y (mm)
        center_z: Center Z (mm)
        axis: Axis ("X", "Y", "Z")
    
    Returns:
Result message
    """
    try:
        # Convert input mm to document units
        radius = _convert_mm_to_document_units(radius)
        height = _convert_mm_to_document_units(height)
        center_x = _convert_mm_to_document_units(center_x)
        center_y = _convert_mm_to_document_units(center_y)
        center_z = _convert_mm_to_document_units(center_z)
        
        rootComp = _get_root_component()
        features = rootComp.features
        
        # Select sketch plane and center by axis
        axis_upper = axis.upper()
        if axis_upper == "X":
            # Extrude along X, draw circle on YZ plane
            sketch_plane = rootComp.yZConstructionPlane
            # On YZ plane, center at (0, center_y, center_z)
            # YZ plane at X=0
            center_point = adsk.core.Point3D.create(0.0, center_y, center_z)
            # After extrude, center at (height/2, center_y, center_z)
            # Move to (center_x, center_y, center_z)
            # Move vector: (center_x - height/2, 0, 0)
            move_x = center_x - height / 2
            move_y = 0.0
            move_z = 0.0
        elif axis_upper == "Y":
            # Extrude along Y, draw on XZ plane
            sketch_plane = rootComp.xZConstructionPlane
            # On XZ plane, center (center_x, 0, center_z)
            # XZ at Y=0
            center_point = adsk.core.Point3D.create(center_x, 0.0, center_z)
            # Center at (center_x, height/2, center_z)
            # Move to (center_x, center_y, center_z)
            # Move vector: (0, center_y - height/2, 0)
            move_x = 0.0
            move_y = center_y - height / 2
            move_z = 0.0
        else:  # Z axis (default)
            # Extrude along Z
            # If center_z != 0, create construction plane at target Z
            if abs(center_z) > 1e-9:
                # Create construction plane at target Z
                # Use XY plane as reference
                base_plane = rootComp.xYConstructionPlane
                # Create offset plane
                planes = rootComp.constructionPlanes
                plane_input = planes.createInput()
                # Create offset
                offset_value = adsk.core.ValueInput.createByReal(center_z)
                plane_input.setByOffset(base_plane, offset_value)
                sketch_plane = planes.add(plane_input)
                # Center at (center_x, center_y, center_z) on offset plane
                center_point = adsk.core.Point3D.create(center_x, center_y, center_z)
                # Sketch at Z, center at (cx,cy,cz+height/2) after extrude
                # Move down height/2 for target center
                # Move vector: (0, 0, -height/2)
                move_x = 0.0
                move_y = 0.0
                move_z = -height / 2
            else:
                # center_z=0: use default XY plane
                sketch_plane = rootComp.xYConstructionPlane
                center_point = adsk.core.Point3D.create(center_x, center_y, 0.0)
                # Center at (cx, cy, height/2)
                # center_z=0, no move needed
                move_x = 0.0
                move_y = 0.0
                move_z = 0.0
        
        # Create sketch
        sketches = rootComp.sketches
        sketch = sketches.add(sketch_plane)
        
        # Draw circle
        circles = sketch.sketchCurves.sketchCircles
        circle = circles.addByCenterRadius(center_point, radius)
        
        # Get profile
        profiles = sketch.profiles
        if profiles.count == 0:
            raise Exception("Cannot create circular profile")
        
        profile = profiles.item(0)
        
        # Create extrude feature
        extrude_features = features.extrudeFeatures
        
        # Create extrude input
        extrude_input = extrude_features.createInput(
            profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        
        # Set extrude distance
        distance_input = adsk.core.ValueInput.createByReal(abs(height))
        extrude_input.setDistanceExtent(False, distance_input)
        
        # Create extrude feature
        # Fusion extrude dir is sketch plane normal
        # YZ plane (X axis): normal (1,0,0); XZ (Y): (0,1,0); XY (Z): (0,0,1); default extrude dir ok
        extrude_feature = extrude_features.add(extrude_input)
        
        # Check extrude success
        if not extrude_feature:
            raise Exception("Extrude feature creation failed")
        
        # Get created body
        if extrude_feature.bodies.count == 0:
            raise Exception("No body created after extrude")
        
        body = extrude_feature.bodies.item(0)
        
        # Name body edges
        _name_edges(body)
        
        # If body needs to be moved to correct position
        if abs(move_x) > 1e-9 or abs(move_y) > 1e-9 or abs(move_z) > 1e-9:
            # Move body to target position
            move_features = features.moveFeatures
            
            # Create body collection
            bodies_collection = adsk.core.ObjectCollection.create()
            bodies_collection.add(body)
            
            # Create transform matrix
            transform = adsk.core.Matrix3D.create()
            transform.translation = adsk.core.Vector3D.create(move_x, move_y, move_z)
            
            # Create move input (first param: ObjectCollection)
            move_feature_input = move_features.createInput(
                bodies_collection,
                transform
            )
            
            # Execute move
            move_feature = move_features.add(move_feature_input)
            
            # Check move success
            if not move_feature:
                raise Exception(f"Move body failed, vector: ({move_x}, {move_y}, {move_z})")
        
        if name:
            body.name = name
        return f"Cylinder created at ({center_x}, {center_y}, {center_z}), radius {radius}, height {height}, axis {axis_upper}"
    
    except Exception as e:
        error_msg = f"Create cylinder failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def create_sphere(radius: float,
                 center_x: float = 0.0, center_y: float = 0.0, center_z: float = 0.0) -> str:
    """
    Create sphere feature
    
    Creates sphere via half-circle sketch and revolve at given coordinates.
    
    Args:
        radius: Radius (mm)
        center_x: Center X (mm)
        center_y: Center Y (mm)
        center_z: Center Z (mm)
    
    Returns:
Result message
    """
    try:
        # Convert input mm to document units
        radius = _convert_mm_to_document_units(radius)
        center_x = _convert_mm_to_document_units(center_x)
        center_y = _convert_mm_to_document_units(center_y)
        center_z = _convert_mm_to_document_units(center_z)
        
        rootComp = _get_root_component()
        features = rootComp.features
        
        # Create sketch on XZ plane (for revolve)
        # If center_y != 0, create offset plane
        if abs(center_y) > 1e-9:
            # Create construction plane at target Y
            base_plane = rootComp.xZConstructionPlane
            planes = rootComp.constructionPlanes
            plane_input = planes.createInput()
            offset_value = adsk.core.ValueInput.createByReal(center_y)
            plane_input.setByOffset(base_plane, offset_value)
            sketch_plane = planes.add(plane_input)
            # On offset plane, center at (center_x, 0, center_z) in sketch coords
            center_point = adsk.core.Point3D.create(center_x, 0.0, center_z)
        else:
            # center_y=0: use default XZ plane
            sketch_plane = rootComp.xZConstructionPlane
            center_point = adsk.core.Point3D.create(center_x, 0.0, center_z)
        
        # Create sketch
        sketches = rootComp.sketches
        sketch = sketches.add(sketch_plane)
        
        # Draw half-circle (from -radius to +radius along X, height radius)
        # Half-circle start/end points (on XZ plane, Y=0)
        # Half-circle from bottom to top, center at (center_x, 0, center_z)
        start_point = adsk.core.Point3D.create(center_x - radius, 0.0, center_z)
        end_point = adsk.core.Point3D.create(center_x + radius, 0.0, center_z)
        # Half-circle top point (radius above center)
        center_arc = adsk.core.Point3D.create(center_x, 0.0, center_z + radius)
        
        # Create arc (half-circle)
        arcs = sketch.sketchCurves.sketchArcs
        arc = arcs.addByThreePoints(start_point, center_arc, end_point)
        
        # Draw line closing start to end (closed profile)
        lines = sketch.sketchCurves.sketchLines
        line = lines.addByTwoPoints(start_point, end_point)
        
        # Get profile
        profiles = sketch.profiles
        if profiles.count == 0:
            raise Exception("Cannot create semicircle profile")
        
        profile = profiles.item(0)
        
        # Create revolve feature
        revolve_features = features.revolveFeatures
        
        # Get rotation axis (Y)
        axis = rootComp.yConstructionAxis
        
        # Create revolve input
        revolve_input = revolve_features.createInput(
            profile,
            axis,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        
        # Set rotation angle to 360 deg
        angle_input = adsk.core.ValueInput.createByReal(math.radians(360.0))
        revolve_input.setAngleExtent(False, angle_input)
        
        # Create revolve feature
        revolve_feature = revolve_features.add(revolve_input)
        
        # Check revolve success
        if not revolve_feature:
            raise Exception("Revolve feature creation failed")
        
        # Get created body
        if revolve_feature.bodies.count == 0:
            raise Exception("No body created after revolve")
        
        body = revolve_feature.bodies.item(0)
        
        # Name body edges
        _name_edges(body)
        
        # If body needs to be moved (Y direction)
        if abs(center_y) > 1e-9:
            # Move body to target position
            move_features = features.moveFeatures
            
            # Create body collection
            bodies_collection = adsk.core.ObjectCollection.create()
            bodies_collection.add(body)
            
            # Create transform matrix (Y translation)
            transform = adsk.core.Matrix3D.create()
            transform.translation = adsk.core.Vector3D.create(0.0, center_y, 0.0)
            
            # Create move input
            move_feature_input = move_features.createInput(
                bodies_collection,
                transform
            )
            
            # Execute move
            move_feature = move_features.add(move_feature_input)
            
            # Check move success
            if not move_feature:
                raise Exception(f"Move body failed, vector: (0, {center_y}, 0)")
        
        return f"Sphere created at ({center_x}, {center_y}, {center_z}), radius {radius}"
    
    except Exception as e:
        error_msg = f"Create sphere failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def extrude(
    profile_name: str,
    distance: float,
    direction: str = "Normal",
    operation: Optional[str] = None,
) -> str:
    """
    Execute extrude operation
    
    Args:
        profile_name: Sketch or profile name to extrude
        distance: Extrusion distance (negative = reverse)
        direction: "Normal", "TwoSides", "Symmetric"
    
    Returns:
Result message
    """
    try:
        if not profile_name or not str(profile_name).strip():
            raise Exception("profile_name required. Create sketch first.")
        rootComp = _get_root_component()
        
        # Find sketch
        sketches = rootComp.sketches
        sketch = None
        for s in sketches:
            if s.name == profile_name:
                sketch = s
                break
        
        if not sketch:
            raise Exception(f"Sketch '{profile_name}' not found. Create sketch with closed profile first.")
        
        # Get profile
        profiles = sketch.profiles
        if profiles.count == 0:
            raise Exception(f"Sketch '{profile_name}' has no extrudable closed profile.")
        
        # Use first profile
        profile = profiles.item(0)
        
        # Create extrude feature
        features = rootComp.features
        extrude_features = features.extrudeFeatures
        
        # Create extrude input
        extrude_input = extrude_features.createInput(
            profile,
            _get_feature_operation(operation),
        )
        
        # Set extrude distance (setDistanceExtent(isSymmetric, distance))
        distance_input = adsk.core.ValueInput.createByReal(abs(distance))
        extrude_input.setDistanceExtent(False, distance_input)
        
        # Set extrusion direction
        if direction == "TwoSides":
            extrude_input.setTwoSidesDistanceExtent(
                adsk.core.ValueInput.createByReal(abs(distance) / 2),
                adsk.core.ValueInput.createByReal(abs(distance) / 2)
            )
        elif direction == "Symmetric":
            extrude_input.setSymmetricDistanceExtent(
                adsk.core.ValueInput.createByReal(abs(distance) / 2)
            )
        
        # Create extrude feature
        extrude_feature = extrude_features.add(extrude_input)
        
        # If new body created, name edges
        if extrude_feature and extrude_feature.bodies.count > 0:
            for i in range(extrude_feature.bodies.count):
                body = extrude_feature.bodies.item(i)
                _name_edges(body)
        
        return f"Extruded {profile_name}, distance: {distance}"
    
    except Exception as e:
        # Raise clear error for HTTP JSON response
        raise Exception(f"Extrude failed: {str(e)}")


def revolve(
    profile_name: str,
    axis: str = "Z",
    angle_degrees: float = 360.0,
    operation: Optional[str] = None,
) -> str:
    """
    Revolve sketch profile around axis.
    """
    try:
        angle_value = float(angle_degrees)
        if angle_value == 0:
            raise Exception("Revolve angle cannot be 0")

        rootComp = _get_root_component()
        profile = _find_profile(rootComp, profile_name)
        axis_obj = _get_axis(rootComp, axis)

        revolve_features = rootComp.features.revolveFeatures
        revolve_input = revolve_features.createInput(
            profile,
            axis_obj,
            _get_feature_operation(operation),
        )

        angle_input = adsk.core.ValueInput.createByReal(math.radians(angle_value))
        revolve_input.setAngleExtent(False, angle_input)
        revolve_feature = revolve_features.add(revolve_input)

        # If new body created, name edges
        if revolve_feature and hasattr(revolve_feature, 'bodies') and revolve_feature.bodies.count > 0:
            for i in range(revolve_feature.bodies.count):
                body = revolve_feature.bodies.item(i)
                _name_edges(body)

        return f"Revolved {profile_name} around {axis.upper()} axis, angle {angle_value}°"
    except Exception as e:
        raise Exception(f"Revolve failed: {str(e)}")


def sweep(
    profile_name: str,
    path_sketch: str,
    operation: Optional[str] = None,
) -> str:
    """
    Sweep profile along path sketch.
    """
    try:
        if not path_sketch:
            raise Exception("path_sketch required")

        rootComp = _get_root_component()
        profile = _find_profile(rootComp, profile_name)
        path_sk = _find_sketch(rootComp, path_sketch)

        curves = adsk.core.ObjectCollection.create()
        sketch_curves = path_sk.sketchCurves
        for i in range(sketch_curves.count):
            curves.add(sketch_curves.item(i))

        if curves.count == 0:
            raise Exception(f"Sketch '{path_sketch}' has no path curves")

        path = adsk.fusion.Path.create(curves, adsk.fusion.ChainingOptions.connectedChaining)

        sweep_features = rootComp.features.sweepFeatures
        sweep_input = sweep_features.createInput(
            profile,
            path,
            _get_feature_operation(operation),
        )
        sweep_feature = sweep_features.add(sweep_input)

        # If new body created, name edges
        if sweep_feature and hasattr(sweep_feature, 'bodies') and sweep_feature.bodies.count > 0:
            for i in range(sweep_feature.bodies.count):
                body = sweep_feature.bodies.item(i)
                _name_edges(body)

        return f"Swept {profile_name} along sketch {path_sketch}"
    except Exception as e:
        raise Exception(f"Sweep failed: {str(e)}")


def loft(section_profiles: List[str], operation: Optional[str] = None) -> str:
    """
    Loft through multiple section sketches.
    """
    try:
        if len(section_profiles) < 2:
            raise Exception("Loft requires at least two section sketches")

        rootComp = _get_root_component()
        loft_features = rootComp.features.loftFeatures
        loft_input = loft_features.createInput(_get_feature_operation(operation))

        for profile_name in section_profiles:
            profile = _find_profile(rootComp, profile_name)
            loft_input.loftSections.add(profile)

        loft_feature = loft_features.add(loft_input)
        
        # If new body created, name edges
        if loft_feature and hasattr(loft_feature, 'bodies') and loft_feature.bodies.count > 0:
            for i in range(loft_feature.bodies.count):
                body = loft_feature.bodies.item(i)
                _name_edges(body)
        
        return f"Loft completed with {len(section_profiles)} sections"
    except Exception as e:
        raise Exception(f"Loft failed: {str(e)}")


def fillet(
    body_name: str,
    radius: float,
    edge_indices: Optional[Iterable[int]] = None,
) -> str:
    """
    Add fillet to body edges.
    """
    try:
        radius_value = float(radius)
        if radius_value <= 0:
            raise Exception("Fillet radius must be > 0")

        rootComp = _get_root_component()
        body = _find_body(rootComp, body_name)
        edges = _collect_edges(body, edge_indices)

        fillet_features = rootComp.features.filletFeatures
        fillet_input = fillet_features.createInput()
        fillet_input.addConstantRadiusEdgeSet(
            edges,
            adsk.core.ValueInput.createByReal(radius_value),
            False,
        )
        fillet_features.add(fillet_input)

        return f"Fillet applied to {body_name}, radius {radius_value}"
    except Exception as e:
        raise Exception(f"Fillet failed: {str(e)}")


def chamfer(
    body_name: str,
    distance: float,
    edge_indices: Optional[Iterable[int]] = None,
) -> str:
    """
    Add chamfer to body edges.
    """
    try:
        distance_value = float(distance)
        if distance_value <= 0:
            raise Exception("Chamfer distance must be > 0")

        rootComp = _get_root_component()
        body = _find_body(rootComp, body_name)
        edges = _collect_edges(body, edge_indices)

        chamfer_features = rootComp.features.chamferFeatures
        chamfer_input = chamfer_features.createInput()
        chamfer_input.chamferEdgeSets.addEqualDistanceChamferEdgeSet(
            edges,
            adsk.core.ValueInput.createByReal(distance_value),
        )
        chamfer_features.add(chamfer_input)

        return f"Chamfer applied to {body_name}, distance {distance_value}"
    except Exception as e:
        raise Exception(f"Chamfer failed: {str(e)}")


def shell(
    body_name: str,
    thickness: float,
    face_indices: Optional[Iterable[int]] = None,
) -> str:
    """
    Perform shell operation on body.
    """
    try:
        thickness_value = float(thickness)
        if thickness_value <= 0:
            raise Exception("Shell thickness must be > 0")

        rootComp = _get_root_component()
        body = _find_body(rootComp, body_name)
        thickness_doc = _convert_mm_to_document_units(thickness_value)

        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)
        faces = _collect_faces(body, face_indices)

        shell_features = rootComp.features.shellFeatures
        shell_input = shell_features.createInput(bodies)
        if faces.count > 0:
            shell_input.removeFaces = faces
        shell_input.insideThickness = adsk.core.ValueInput.createByReal(thickness_doc)
        shell_features.add(shell_input)

        return f"Shell applied to {body_name}, thickness {thickness_value}mm"
    except Exception as e:
        raise Exception(f"Shell failed: {str(e)}")


def combine(
    target_body: str,
    tool_bodies: List[str],
    operation: str = "Cut",
    keep_tools: bool = False,
) -> str:
    """
    Perform boolean operation on bodies.
    """
    try:
        if not tool_bodies:
            raise Exception("At least one tool body required for boolean")

        rootComp = _get_root_component()
        target = _find_body(rootComp, target_body)

        tools = adsk.core.ObjectCollection.create()
        for name in tool_bodies:
            tools.add(_find_body(rootComp, name))

        combine_features = rootComp.features.combineFeatures
        combine_input = combine_features.createInput(target, tools)
        combine_input.operation = _get_feature_operation(operation)
        combine_input.isKeepToolBodies = bool(keep_tools)
        combine_features.add(combine_input)

        return f"Boolean {operation} applied to {target_body} with {len(tool_bodies)} tool body(ies)"
    except Exception as e:
        raise Exception(f"Boolean operation failed: {str(e)}")


def rotate_body(
    body_name: str,
    angle_degrees: float,
    axis: str = "Z",
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = 0.0,
) -> str:
    """
    Rotate existing body.
    
    Args:
        body_name: Body name
        angle_degrees: Rotation angle (degrees)
        axis: Rotation axis ("X", "Y", "Z")
        center_x/y/z: Rotation center (optional, default 0.0)
    
    Returns:
Result message
    """
    try:
        angle_value = float(angle_degrees)
        if angle_value == 0:
            raise Exception("Revolve angle cannot be 0")
        
        rootComp = _get_root_component()
        body = _find_body(rootComp, body_name)

        center_x_doc = _convert_mm_to_document_units(center_x)
        center_y_doc = _convert_mm_to_document_units(center_y)
        center_z_doc = _convert_mm_to_document_units(center_z)

        axis_obj = _get_axis(rootComp, axis)
        axis_geometry = axis_obj.geometry
        center_point = adsk.core.Point3D.create(center_x_doc, center_y_doc, center_z_doc)

        transform = adsk.core.Matrix3D.create()
        transform.setToRotation(
            math.radians(angle_value),
            axis_geometry,
            center_point
        )

        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)
        move_features = rootComp.features.moveFeatures
        move_input = move_features.createInput2(bodies)
        move_input.defineAsFreeMove(transform)
        move_features.add(move_input)
        
        return f"Rotated {body_name} around {axis.upper()} axis by {angle_value}°"
    except Exception as e:
        raise Exception(f"Rotate body failed: {str(e)}")


def move_body(
    body_name: str,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
) -> str:
    """
    Translate existing body.

    Args:
        body_name: Body name
        offset_x/y/z: Offset in mm

    Returns:
Result message
    """
    try:
        if abs(offset_x) < 1e-9 and abs(offset_y) < 1e-9 and abs(offset_z) < 1e-9:
            raise Exception("Offset cannot be all zero. Specify offset_x/offset_y/offset_z")

        rootComp = _get_root_component()
        body = _find_body(rootComp, body_name)

        offset_x_doc = _convert_mm_to_document_units(offset_x)
        offset_y_doc = _convert_mm_to_document_units(offset_y)
        offset_z_doc = _convert_mm_to_document_units(offset_z)

        transform = adsk.core.Matrix3D.create()
        transform.translation = adsk.core.Vector3D.create(offset_x_doc, offset_y_doc, offset_z_doc)

        bodies = adsk.core.ObjectCollection.create()
        bodies.add(body)
        move_features = rootComp.features.moveFeatures
        move_input = move_features.createInput2(bodies)
        move_input.defineAsFreeMove(transform)
        move_features.add(move_input)

        return f"Moved body '{body_name}' (X:{offset_x}, Y:{offset_y}, Z:{offset_z}) mm"
    except Exception as e:
        raise Exception(f"Move body failed: {str(e)}")


def get_document_content() -> dict:
    """
    Get document content: bodies, sketches, features.
    
    Returns:
        Dict with document details
    """
    try:
        rootComp = _get_root_component()
        design = _get_design()
        
        # Get all body info
        bodies = []
        for i in range(rootComp.bRepBodies.count):
            body = rootComp.bRepBodies.item(i)
            try:
                # Get body bounding box
                bbox = body.boundingBox
                body_name_for_edges = body.name or f"Body{i}"
                body_info = {
                    "name": body_name_for_edges,
                    "index": i,
                    "volume": body.volume if hasattr(body, 'volume') else None,
                    "area": body.area if hasattr(body, 'area') else None,
                    "faces_count": body.faces.count,
                    "edges_count": body.edges.count,
                    "edges": [],
                }
                # Collect edge index and name for later use
                for ei in range(body.edges.count):
                    try:
                        edge = body.edges.item(ei)
                        edge_name = edge.name if (edge.name and edge.name.strip()) else f"{body_name_for_edges}_edge_{ei}"
                        body_info["edges"].append({"index": ei, "name": edge_name})
                    except Exception:
                        body_info["edges"].append({"index": ei, "name": f"{body_name_for_edges}_edge_{ei}"})

                if bbox:
                    # Compute body center (bbox centroid): (min+max)/2
                    center_x_doc = (bbox.minPoint.x + bbox.maxPoint.x) / 2
                    center_y_doc = (bbox.minPoint.y + bbox.maxPoint.y) / 2
                    center_z_doc = (bbox.minPoint.z + bbox.maxPoint.z) / 2
                    
                    # Convert to mm
                    center_x_mm = _convert_document_units_to_mm(center_x_doc)
                    center_y_mm = _convert_document_units_to_mm(center_y_doc)
                    center_z_mm = _convert_document_units_to_mm(center_z_doc)
                    
                    body_info["bounding_box"] = {
                        "min_x": bbox.minPoint.x,
                        "min_y": bbox.minPoint.y,
                        "min_z": bbox.minPoint.z,
                        "max_x": bbox.maxPoint.x,
                        "max_y": bbox.maxPoint.y,
                        "max_z": bbox.maxPoint.z,
                    }
                    body_info["center"] = {
                        "x": center_x_mm,
                        "y": center_y_mm,
                        "z": center_z_mm,
                    }
                    body_info["size"] = {
                        "width": _convert_document_units_to_mm(bbox.maxPoint.x - bbox.minPoint.x),
                        "height": _convert_document_units_to_mm(bbox.maxPoint.y - bbox.minPoint.y),
                        "depth": _convert_document_units_to_mm(bbox.maxPoint.z - bbox.minPoint.z),
                    }
                else:
                    body_info["bounding_box"] = None
                    body_info["center"] = None
                    body_info["size"] = None
                
                bodies.append(body_info)
            except Exception as e:
                bodies.append({
                    "name": body.name or f"Body{i}",
                    "index": i,
                    "error": str(e)
                })
        
        # Get all sketch info
        sketches = []
        for i in range(rootComp.sketches.count):
            sketch = rootComp.sketches.item(i)
            try:
                profiles_count = sketch.profiles.count
                sketch_curves_count = sketch.sketchCurves.count
                sketches.append({
                    "name": sketch.name or f"Sketch{i}",
                    "index": i,
                    "profiles_count": profiles_count,
                    "curves_count": sketch_curves_count,
                    "is_visible": sketch.isVisible,
                })
            except Exception as e:
                sketches.append({
                    "name": sketch.name or f"Sketch{i}",
                    "index": i,
                    "error": str(e)
                })
        
        # Get all feature info
        features = []
        for i in range(rootComp.features.count):
            feature = rootComp.features.item(i)
            try:
                # Try multiple methods to get feature type
                feature_type = "Unknown"
                if hasattr(feature, 'classType'):
                    try:
                        feature_type = feature.classType().name
                    except Exception:
                        pass
                if feature_type == "Unknown" and hasattr(feature, 'objectType'):
                    try:
                        feature_type = str(feature.objectType)
                    except Exception:
                        pass
                if feature_type == "Unknown":
                    feature_type = type(feature).__name__
                
                features.append({
                    "name": feature.name or f"Feature{i}",
                    "index": i,
                    "type": feature_type,
                    "is_suppressed": feature.isSuppressed if hasattr(feature, 'isSuppressed') else None,
                })
            except Exception as e:
                features.append({
                    "name": feature.name or f"Feature{i}",
                    "index": i,
                    "error": str(e)
                })
        
        return {
            "bodies": bodies,
            "sketches": sketches,
            "features": features,
            "bodies_count": len(bodies),
            "sketches_count": len(sketches),
            "features_count": len(features),
        }
    except Exception as e:
        raise Exception(f"Get document content failed: {str(e)}")


def modify_body_dimensions(
    body_name: str,
    entity_type: str,
    # Box params
    width: Optional[float] = None,
    height: Optional[float] = None,
    depth: Optional[float] = None,
    # Cylinder params
    radius: Optional[float] = None,
    cylinder_height: Optional[float] = None,
    cylinder_axis: str = "Z",
) -> str:
    """
    Modify body dimensions.
    
    Deletes old body and creates new-sized body at same position.
    
    Args:
        body_name: Body name to modify
        entity_type: "box" or "cylinder"
        width/height/depth: Box dims in mm (box only)
        radius/cylinder_height/cylinder_axis: Cylinder params (cylinder only)
    
    Returns:
        Result message
    """
    try:
        rootComp = _get_root_component()
        
        # Find body to modify
        body = _find_body(rootComp, body_name)
        
        # Get body bounding box and center
        bbox = body.boundingBox
        if not bbox:
            raise Exception(f"Cannot get bounding box for body '{body_name}'")
        
        # Compute body center (doc units)
        center_x_doc = (bbox.minPoint.x + bbox.maxPoint.x) / 2
        center_y_doc = (bbox.minPoint.y + bbox.maxPoint.y) / 2
        center_z_doc = (bbox.minPoint.z + bbox.maxPoint.z) / 2
        
        # Convert doc coords to mm (create_box expects mm)
        center_x = _convert_document_units_to_mm(center_x_doc)
        center_y = _convert_document_units_to_mm(center_y_doc)
        center_z = _convert_document_units_to_mm(center_z_doc)
        
        # Compute new size by entity type (unprovided dims preserved)
        entity_type_lower = entity_type.lower()
        if entity_type_lower == "box":
            if width is None and height is None and depth is None:
                raise Exception("Modify box requires at least one of width, height, depth")
            # Get current size from bbox (mm)
            current_w = _convert_document_units_to_mm(bbox.maxPoint.x - bbox.minPoint.x)
            current_h = _convert_document_units_to_mm(bbox.maxPoint.y - bbox.minPoint.y)
            current_d = _convert_document_units_to_mm(bbox.maxPoint.z - bbox.minPoint.z)
            # Unprovided dims use current values
            final_width = width if width is not None else current_w
            final_height = height if height is not None else current_h
            final_depth = depth if depth is not None else current_d
            if final_width <= 0 or final_height <= 0 or final_depth <= 0:
                raise Exception(f"Box dimensions must be > 0. width={final_width}, height={final_height}, depth={final_depth}")
            width, height, depth = final_width, final_height, final_depth
        elif entity_type_lower == "cylinder":
            if radius is None and cylinder_height is None:
                raise Exception("Cylinder requires at least one of radius, cylinder_height")
            if radius is None or cylinder_height is None:
                ext_x = _convert_document_units_to_mm(bbox.maxPoint.x - bbox.minPoint.x)
                ext_y = _convert_document_units_to_mm(bbox.maxPoint.y - bbox.minPoint.y)
                ext_z = _convert_document_units_to_mm(bbox.maxPoint.z - bbox.minPoint.z)
                if radius is None:
                    radius = max(ext_x, ext_y, ext_z) / 2.0
                if cylinder_height is None:
                    cylinder_height = min(ext_x, ext_y, ext_z)

        # Delete old body
        body.deleteMe()

        # Create new body by type (name preserved for tool refs)
        if entity_type_lower == "box":
            create_box(width, height, depth, center_x, center_y, center_z, name=body_name)
            return f"Modified body '{body_name}' to {width}mm x {height}mm x {depth}mm, position unchanged"
        elif entity_type_lower == "cylinder":
            if radius <= 0 or cylinder_height <= 0:
                raise Exception(f"Cylinder radius and height must be > 0. radius={radius}, height={cylinder_height}")
            
            create_cylinder(radius, cylinder_height, center_x, center_y, center_z, cylinder_axis, name=body_name)
            return f"Modified body '{body_name}' to radius {radius}mm, height {cylinder_height}mm, position unchanged"
        else:
            raise Exception(f"Unsupported entity_type: {entity_type}, use box or cylinder")
    
    except Exception as e:
        error_msg = f"Modify body dimensions failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


def delete_body(body_name: str) -> str:
    """
    Delete specified body.
    
    Args:
        body_name: Body name to delete
    
    Returns:
Result message
    """
    try:
        rootComp = _get_root_component()
        
        # Find body to delete
        body = _find_body(rootComp, body_name)
        
        # Delete body
        body.deleteMe()
        
        return f"Successfully deleted body '{body_name}'"
    
    except Exception as e:
        error_msg = f"Delete body failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg)


