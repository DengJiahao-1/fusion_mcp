"""Feature operation tools: extrude, revolve, sweep, loft"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client
from mcp_server.tools.helpers import handle_api_response

__all__ = ["register"]


def register(app: FastMCP, client: Fusion360Client) -> None:
    """Register feature operation tools."""

    @app.tool()
    async def extrude(
        profile_name: str,
        distance: float,
        direction: str = "Normal",
        operation: Optional[str] = None,
    ) -> str:
        """
        Extrude sketch profile to 3D entity.
        
        [Usage - When to Use]
        - User wants to extrude an EXISTING sketch profile to create 3D shape
        - Sketch must already exist (created with create_sketch and drawn shapes)
        - Sketch must have closed profile (rectangle, circle, etc.)
        - This is for sketch-based modeling workflow
        
        [Don't Use When - Common Mistakes]
        - ❌ User says "创建一个长方体" / "创建一个立方体" → use create_box instead (no sketch needed)
        - ❌ User says "创建一个圆柱体" → use create_cylinder instead (no sketch needed)
        - ❌ create_box/create_cylinder already succeeded → task is complete, don't call this tool
        - ❌ No sketch exists yet → first create sketch with create_sketch, then draw shapes, then extrude
        - ❌ Sketch doesn't have closed profile → cannot extrude
        - ❌ After create_box succeeds → DO NOT call this tool, create_box already created the box
        
        [Required Params]:
        - profile_name: Sketch name to extrude (must exist, must have closed profile)
          → Get sketch name from get_document_content if user mentions sketch1/sketch2
        - distance: Extrusion distance (positive=forward, negative=backward)
        
        [Optional Params]:
        - direction: Extrusion direction (default: "Normal")
          Values: "Normal" (one side), "TwoSides" (both sides), "Symmetric" (symmetric)
        
        [Workflow]
        1. Create sketch: create_sketch(plane="XY")
        2. Draw shapes in sketch (rectangles, circles, etc.) - use sketch drawing tools
        3. Extrude: extrude(profile_name="Sketch1", distance=10)
        
        [Examples]
        ✅ "拉伸草图1，距离10mm" → extrude(profile_name="Sketch1", distance=10)
        ✅ "将草图2拉伸20mm" → extrude(profile_name="Sketch2", distance=20)
        
        [Note]
        - Extrudes existing sketch, not creates new shape directly
        - For creating box/cylinder without sketch, use create_box/create_cylinder
        - Unit: mm
        """
        payload: Dict[str, Any] = {
            "profile_name": profile_name,
            "distance": distance,
            "direction": direction,
            "operation": operation,
        }

        return await handle_api_response(
            client,
            "/api/feature/extrude",
            payload,
            default_message=f"Extruded {profile_name}, distance: {distance}",
            check_success=False,
        )

    @app.tool()
    async def revolve(
        profile_name: str,
        angle_degrees: float,
        axis: str = "Z",
        operation: Optional[str] = None,
    ) -> str:
        """
        Revolve sketch profile around axis to create 3D entity.
        
        [Usage - When to Use]
        - User wants to revolve an EXISTING sketch profile around an axis to create 3D shape
        - Sketch must already exist (created with create_sketch and drawn shapes)
        - Sketch must have closed profile
        - This creates a new 3D shape by rotating a 2D profile (like lathe operation)
        
        [Don't Use When - Common Mistakes]
        - ❌ User says "旋转实体1" / "旋转长方体" → use rotate_body instead (rotates existing 3D entity)
        - ❌ No sketch exists yet → first create sketch, then draw profile, then revolve
        - ❌ Sketch doesn't have closed profile → cannot revolve
        - ❌ User wants to rotate an existing 3D body → use rotate_body, NOT this tool
        
        [Required Params]:
        - profile_name: Sketch name to revolve (must exist, must have closed profile)
          → Get sketch name from get_document_content if user mentions sketch1/sketch2
        - angle_degrees: Rotation angle in degrees
          Example: 360 = full rotation, 180 = half rotation
        
        [Optional Params]:
        - axis: Rotation axis "X"/"Y"/"Z" (default: "Z")
        - operation: Feature operation type
          Values: "NewBody" (new body), "Join" (merge), "Cut" (cut), "Intersect" (intersect)
        
        [Workflow]
        1. Create sketch: create_sketch(plane="XY")
        2. Draw profile in sketch (half profile for revolution)
        3. Revolve: revolve(profile_name="Sketch1", angle_degrees=360, axis="Z")
        
        [Examples]
        ✅ "revolve Sketch1 360 deg" → revolve(profile_name="Sketch1", angle_degrees=360)
        ✅ "revolve Sketch2 180 deg around Z" → revolve(profile_name="Sketch2", angle_degrees=180, axis="Z")
        
        [Note]
        - Revolves sketch profile (2D), not existing 3D entity
        - To rotate existing 3D entity, use rotate_body tool
        - This creates new 3D shape, rotate_body rotates existing shape
        """
        payload: Dict[str, Any] = {
            "profile_name": profile_name,
            "angle_degrees": angle_degrees,
            "axis": axis,
            "operation": operation,
        }

        return await handle_api_response(
            client,
            "/api/feature/revolve",
            payload,
            default_message=f"Revolved {profile_name}, angle {angle_degrees}°",
            check_success=False,
        )

    @app.tool()
    async def sweep(
        profile_name: str,
        path_sketch: str,
        operation: Optional[str] = None,
    ) -> str:
        """
        Sweep profile along path sketch to create 3D entity.
        
        [Usage - When to Use]
        - User wants to sweep a profile sketch along a path sketch to create 3D shape
        - Both profile and path sketches must already exist
        - This creates a 3D shape by moving a 2D profile along a path (like pipe/tube)
        
        [Don't Use When - Common Mistakes]
        - ❌ No sketches exist yet → first create sketches with create_sketch
        - ❌ Only one sketch exists → need both profile and path sketches
        - ❌ User wants to create simple box/cylinder → use create_box/create_cylinder instead
        
        [Required Params]:
        - profile_name: Sketch name for profile (must exist)
          → Get sketch name from get_document_content if user mentions "草图1" / "草图2"
        - path_sketch: Sketch name for path (must exist)
          → Get sketch name from get_document_content
        
        [Optional Params]:
        - operation: Feature operation type
          Values: "NewBody", "Join", "Cut", "Intersect"
        
        [Workflow]
        1. Create profile sketch: create_sketch(plane="XY") - draw circle/rectangle
        2. Create path sketch: create_sketch(plane="XY") - draw path curve
        3. Sweep: sweep(profile_name="Sketch1", path_sketch="Sketch2")
        
        [Examples]
        ✅ "扫掠草图1沿草图2" → sweep(profile_name="Sketch1", path_sketch="Sketch2")
        
        [Note]
        - Sweeps profile along path to create 3D entity
        - Both sketches must exist before calling this tool
        """
        payload: Dict[str, Any] = {
            "profile_name": profile_name,
            "path_sketch": path_sketch,
            "operation": operation,
        }

        return await handle_api_response(
            client,
            "/api/feature/sweep",
            payload,
            default_message="Sweep completed",
            check_success=False,
        )

    @app.tool()
    async def loft(
        section_profiles: List[str],
        operation: Optional[str] = None,
    ) -> str:
        """
        Loft through multiple section sketches to create 3D entity.
        
        [Usage - When to Use]
        - User wants to create 3D shape by lofting through multiple section sketches
        - At least 2 section sketches must already exist
        - This creates smooth transition between different cross-sections
        
        [Don't Use When - Common Mistakes]
        - ❌ Less than 2 sketches exist → need at least 2 section sketches
        - ❌ User wants to create simple box/cylinder → use create_box/create_cylinder instead
        - ❌ Only one sketch exists → need multiple section sketches
        
        [Required Params]:
        - section_profiles: List of sketch names for sections (must exist, at least 2)
          → Get sketch names from get_document_content
          → Example: ["Sketch1", "Sketch2", "Sketch3"]
        
        [Optional Params]:
        - operation: Feature operation type
          Values: "NewBody", "Join", "Cut", "Intersect"
        
        [Workflow]
        1. Create multiple section sketches: create_sketch(plane="XY") - draw different cross-sections
        2. Loft: loft(section_profiles=["Sketch1", "Sketch2", "Sketch3"])
        
        [Examples]
        ✅ "放样草图1、草图2、草图3" → loft(section_profiles=["Sketch1", "Sketch2", "Sketch3"])
        
        [Note]
        - Creates 3D entity by lofting through section profiles
        - Requires at least 2 section sketches
        - All sketches must exist before calling this tool
        """
        payload: Dict[str, Any] = {
            "section_profiles": section_profiles,
            "operation": operation,
        }

        return await handle_api_response(
            client,
            "/api/feature/loft",
            payload,
            default_message="Loft completed",
            check_success=False,
        )

