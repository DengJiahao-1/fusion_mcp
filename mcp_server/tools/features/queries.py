"""
Query tools.

Includes: get_document_content
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client, Fusion360ClientError

__all__ = ["register"]

_last_content_hash: Optional[str] = None


def register(app: FastMCP, client: Fusion360Client) -> None:
    """Register query tools."""

    @app.tool()
    async def get_document_content() -> str:
        """
        Read current Fusion 360 document content (bodies, sketches, features).
        
        [Important] Call ONCE before specifying entity names!
        When user mentions "Body1" / "Body2" / "Sketch1" / "Sketch2":
        1. Call this tool ONCE to get entity/sketch list
        2. Find matching entity/sketch name from results (check "Name:" field)
        3. Use exact name in other tools (e.g., create_entity_relative, modify_body_dimensions)
        4. Don't call again! Reuse the results in the same turn.
        
        [When to Use]
        - User mentions entity/sketch by name/number: "Body1", "Body2", "Sketch1", "first entity"
        - Before calling tools that need entity/sketch names:
          * create_entity_relative (needs base_body_name)
          * modify_body_dimensions (needs body_name)
          * rotate_body (needs body_name)
          * fillet/chamfer/shell (needs body_name)
          * combine (needs target_body and tool_bodies)
          * delete_body (needs body_name)
          * extrude/revolve (needs profile_name)
          * delete_sketch (needs sketch_name)
        
        [When NOT to Use]
        - User says "create a box" (no entity name mentioned) -> use create_box directly
        - User says "create a cylinder" (no entity name mentioned) -> use create_cylinder directly
        - Already called in this turn -> reuse previous results, don't call again
        
        [Returns]
        - Bodies: name, volume, area, bounding box, face/edge count, edges list (index+name for fillet/chamfer)
        - Sketches: name, profile/curve count, visibility
        - Features: name, type, suppressed status
        
        [Name Matching]
        - User says "Body1" -> find name containing "1" or first entity (from "Name: Body1" field)
        - User says "first entity" -> use first entity in list
        - User says "last entity" -> use last entity in list
        - Extract exact name from "Name: XXX" field in results
        
        [Note]
        - Returns structured text with all document objects
        - If content unchanged since last call, returns brief message only
        - Call ONCE per turn, reuse results for all entity name lookups
        - This tool is for getting entity/sketch names, not for creating entities
        """
        global _last_content_hash
        
        try:
            result = await client.request("/api/document/content", method="GET")
            
            if not result.get("success", False):
                error = result.get("error", "Unknown error")
                return f"Failed to get document content: {error}"
            
            content_for_hash = {
                "bodies": result.get("bodies", []),
                "sketches": result.get("sketches", []),
                "features": result.get("features", []),
                "bodies_count": result.get("bodies_count", 0),
                "sketches_count": result.get("sketches_count", 0),
                "features_count": result.get("features_count", 0),
            }
            content_json = json.dumps(content_for_hash, sort_keys=True, ensure_ascii=False)
            current_hash = hashlib.md5(content_json.encode('utf-8')).hexdigest()
            
            if _last_content_hash == current_hash:
                bodies_count = result.get("bodies_count", 0)
                sketches_count = result.get("sketches_count", 0)
                features_count = result.get("features_count", 0)
                return f"Document content unchanged (bodies: {bodies_count}, sketches: {sketches_count}, features: {features_count})"
            
            _last_content_hash = current_hash
            
            output_lines = []
            output_lines.append("=== Fusion 360 Document Content ===\n")
            
            bodies = result.get("bodies", [])
            bodies_count = result.get("bodies_count", 0)
            output_lines.append(f"Body count: {bodies_count}")
            for i, body in enumerate(bodies, 1):
                output_lines.append(f"\nBody {i}:")
                output_lines.append(f"  Name: {body.get('name', 'N/A')}")
                if "error" in body:
                    output_lines.append(f"  Error: {body['error']}")
                else:
                    if body.get("volume") is not None:
                        output_lines.append(f"  Volume: {body['volume']:.2f}")
                    if body.get("area") is not None:
                        output_lines.append(f"  Area: {body['area']:.2f}")
                    center = body.get("center")
                    if center:
                        output_lines.append(f"  Center: ({center['x']:.2f}, {center['y']:.2f}, {center['z']:.2f}) mm")
                    size = body.get("size")
                    if size:
                        output_lines.append(f"  Size: {size['width']:.2f}mm x {size['height']:.2f}mm x {size['depth']:.2f}mm")
                    bbox = body.get("bounding_box")
                    if bbox:
                        output_lines.append(f"  Bounding box: X[{bbox['min_x']:.2f}, {bbox['max_x']:.2f}], "
                                          f"Y[{bbox['min_y']:.2f}, {bbox['max_y']:.2f}], "
                                          f"Z[{bbox['min_z']:.2f}, {bbox['max_z']:.2f}]")
                    output_lines.append(f"  Faces: {body.get('faces_count', 0)}")
                    output_lines.append(f"  Edges: {body.get('edges_count', 0)}")
                    edges = body.get("edges", [])
                    if edges:
                        edges_str = ", ".join(f"[{e['index']}]{e['name']}" for e in edges)
                        output_lines.append(f"  Edges list: {edges_str}")
            
            sketches = result.get("sketches", [])
            sketches_count = result.get("sketches_count", 0)
            output_lines.append(f"\n\nSketch count: {sketches_count}")
            for i, sketch in enumerate(sketches, 1):
                output_lines.append(f"\nSketch {i}:")
                output_lines.append(f"  Name: {sketch.get('name', 'N/A')}")
                if "error" in sketch:
                    output_lines.append(f"  Error: {sketch['error']}")
                else:
                    output_lines.append(f"  Profiles: {sketch.get('profiles_count', 0)}")
                    output_lines.append(f"  Curves: {sketch.get('curves_count', 0)}")
                    output_lines.append(f"  Visible: {'Yes' if sketch.get('is_visible', False) else 'No'}")
            
            features = result.get("features", [])
            features_count = result.get("features_count", 0)
            output_lines.append(f"\n\nFeature count: {features_count}")
            for i, feature in enumerate(features, 1):
                output_lines.append(f"\nFeature {i}:")
                output_lines.append(f"  Name: {feature.get('name', 'N/A')}")
                if "error" in feature:
                    output_lines.append(f"  Error: {feature['error']}")
                else:
                    output_lines.append(f"  Type: {feature.get('type', 'N/A')}")
                    if feature.get("is_suppressed") is not None:
                        output_lines.append(f"  Suppressed: {'Yes' if feature['is_suppressed'] else 'No'}")
            
            return "\n".join(output_lines)
        except Fusion360ClientError as exc:
            raise RuntimeError(str(exc)) from exc
