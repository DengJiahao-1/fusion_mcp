"""
Modification tools: modify_body_dimensions, rotate_body, move_body
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client
from mcp_server.tools.helpers import (
    EntityType,
    handle_api_response,
    normalize_entity_type,
    parse_box_dimensions,
)

__all__ = ["register"]


def register(app: FastMCP, client: Fusion360Client) -> None:
    """Register modification tools."""

    @app.tool()
    async def modify_body_dimensions(
        body_name: str,
        entity_type: str,
        # Box params
        width: Optional[float] = None,
        height: Optional[float] = None,
        depth: Optional[float] = None,
        # dimensions: [w,h,d] or {width, height, depth}, overrides width/height/depth if provided
        dimensions: Optional[Any] = None,
        size: Optional[Any] = None,  # alias for dimensions
        # Cylinder params
        radius: Optional[float] = None,
        cylinder_height: Optional[float] = None,
        cylinder_axis: str = "Z",
    ) -> str:
        """
        Modify dimensions of existing entity.
        
        [Usage - When to Use]
        - User says "modify/change/adjust entity X dimensions" → use this tool
        - Entity must already exist, requires exact entity name (from get_document_content)
        - This MODIFIES existing entity, keeping same center position
        
        [Don't Use When - Common Mistakes]
        - ❌ User says "创建一个..." / "新建一个..." / "生成一个..."
          → Use create_box/create_cylinder/create_sphere instead (creating new entity)
        - ❌ Entity doesn't exist yet → first create entity with create_box/create_cylinder
        - ❌ User wants to create new entity → use create_box/create_cylinder, NOT this tool
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions body1/body2/entityX:
        1. Call get_document_content ONCE to get entity list
        2. Find matching entity from results (check "名称:" field)
        3. Use exact entity name as body_name, call this tool immediately
        4. Don't call get_document_content again! Reuse the results.
        
        [Required Params]
        - body_name: Entity name to modify (must exist, get from get_document_content)
        - entity_type: "box" or "cylinder"
        
        [Box Params] (when entity_type="box", mm):
        - width/height/depth: provide only changed dims; unchanged ones are preserved
        - dimensions or size: [w,h,d] or {width, height, depth}
        
        [Cylinder Params] (when entity_type="cylinder", mm):
        - radius: Cylinder radius
        - cylinder_height: Cylinder height
        - cylinder_axis: "X"/"Y"/"Z" (default: "Z")
        
        [Parameter Mapping - for box]
        depth (Z-axis), width (X-axis), height (Y-axis)
        Note: No 'length' param; map "length" to width.
        
        [CRITICAL - Shell thickness vs this tool]
        - If "thickness" means hollow shell wall → use shell(thickness=X), NOT this tool
        - This tool modifies primitive dimensions; shell thickness cannot be changed once applied
        
        [How It Works]
        1. Find specified entity
        2. Get entity center position
        3. Delete old entity
        4. Create new entity with new dimensions at same position
        
        [Examples - Correct Usage]
        ✅ "change width to 50" → modify_body_dimensions(body_name="Body1", entity_type="box", width=50)
        ✅ "modify body1 to 10x10x1" → modify_body_dimensions(body_name="Body1", entity_type="box", width=10, height=10, depth=1)
        
        [Examples - Wrong Usage (Don't Use This Tool)]
        ❌ "创建一个高10mm长20mm宽20mm的长方体"
          → Use create_box instead (creating new entity)
          → create_box(width=20, height=20, depth=10)
        
        [Note]
        - Modifies existing entity, not creates new one
        - Entity center position remains unchanged
        - Unit: mm
        - All dimensions must be > 0
        """
        # Normalize entity_type
        final_entity_type = normalize_entity_type(entity_type)
        
        # Parse box dimensions
        final_width, final_height, final_depth = parse_box_dimensions(
            width, height, depth, dimensions, size
        )
        
        payload: Dict[str, Any] = {
            "body_name": body_name,
            "entity_type": final_entity_type,
        }
        
        # Add params by entity type (unprovided dims from add-in bbox)
        if final_entity_type == EntityType.BOX.value:
            if final_width is None and final_height is None and final_depth is None:
                raise ValueError("Box requires at least one of width, height, depth")
            payload["width"] = final_width
            payload["height"] = final_height
            payload["depth"] = final_depth
        elif final_entity_type == EntityType.CYLINDER.value:
            if radius is None and cylinder_height is None:
                raise ValueError("修改圆柱体时需要至少提供一个参数：radius 或 cylinder_height")
            payload["radius"] = radius
            payload["cylinder_height"] = cylinder_height
            payload["cylinder_axis"] = cylinder_axis
        else:
            raise ValueError(f"Unsupported entity_type: {final_entity_type}, use {EntityType.BOX.value} or {EntityType.CYLINDER.value}")

        return await handle_api_response(
            client,
            "/api/feature/modify_body_dimensions",
            payload,
            default_message=f"Successfully modified body '{body_name}' dimensions",
            check_success=True,
        )

    @app.tool()
    async def rotate_body(
        body_name: str,
        angle_degrees: float,
        axis: str = "Z",
        center_x: float = 0.0,
        center_y: float = 0.0,
        center_z: float = 0.0,
    ) -> str:
        """
        Rotate existing 3D entity (box, cylinder, etc.).
        
        [Usage - When to Use]
        - User says "rotate body X" / "rotate entity by N degrees" → use this tool
        - Rotates an EXISTING 3D entity around an axis
        - Entity must already exist, requires exact entity name (from get_document_content)
        
        [Don't Use When - Common Mistakes]
        - ❌ User says "旋转草图" / "旋转轮廓" → use revolve tool instead (revolves 2D sketch profile)
        - ❌ User wants to create 3D shape by rotating 2D profile → use revolve tool
        - ❌ Entity doesn't exist yet → first create entity with create_box/create_cylinder
        
        [Required Params]:
        - body_name: Entity name (must exist, get from get_document_content)
        - angle_degrees: Rotation angle in degrees
          Positive = counterclockwise, negative = clockwise
        
        [Optional Params]:
        - axis: Rotation axis "X"/"Y"/"Z" (default: "Z")
        - center_x/y/z: Rotation center coordinates (default: 0.0)
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions "实体1" / "实体2":
        1. Call get_document_content ONCE
        2. Find matching entity name (check "名称:" field)
        3. Use exact name as body_name
        4. Don't call get_document_content again! Reuse the results.
        
        [Examples - Correct Usage]
        ✅ "rotate body1 30 deg" → rotate_body(body_name="Body1", angle_degrees=30)
        ✅ "rotate around Z by 45 deg" → rotate_body(body_name="Body1", angle_degrees=45, axis="Z")
        
        [Examples - Wrong Usage (Don't Use This Tool)]
        ❌ "旋转草图1创建圆柱体" → use revolve tool (revolves 2D sketch to create 3D shape)
        
        [Note]
        - Rotates existing 3D entity, not sketch profile
        - To revolve sketch profile to create 3D shape, use revolve tool
        - This rotates existing shape, revolve creates new shape from 2D profile
        - Unit: mm, degrees
        """
        payload: Dict[str, Any] = {
            "body_name": body_name,
            "angle_degrees": angle_degrees,
            "axis": axis,
            "center_x": center_x,
            "center_y": center_y,
            "center_z": center_z,
        }

        return await handle_api_response(
            client,
            "/api/feature/rotate_body",
            payload,
            default_message=f"Rotated body {body_name} by {angle_degrees}°",
            check_success=False,
        )

    @app.tool()
    async def move_body(
        body_name: str,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        offset_z: float = 0.0,
    ) -> str:
        """
        Move (translate) existing 3D entity by offset.

        [Usage - When to Use]
        - User says "move body X" / "translate entity" / "move 5mm in X" → use this tool
        - Translates an EXISTING 3D entity by specified offset in X, Y, Z
        - Entity must already exist, requires exact entity name (from get_document_content)

        [Don't Use When]
        - ❌ Entity doesn't exist yet → first create with create_box/create_cylinder
        - ❌ User wants to rotate → use rotate_body instead

        [Required Params]
        - body_name: Entity name (must exist, get from get_document_content)

        [Optional Params - at least one should be non-zero]
        - offset_x: X-axis offset in mm (CN: "X方向/向右")
        - offset_y: Y-axis offset in mm (CN: "Y方向/向前")
        - offset_z: Z-axis offset in mm (CN: "Z方向/向上")

        [Get Entity Name Steps]
        When user mentions "实体1" / "实体2":
        1. Call get_document_content ONCE
        2. Find matching entity name from "Name:" field
        3. Use exact name as body_name

        [Examples]
        ✅ "将实体1向X方向移动10mm" → move_body(body_name="实体1", offset_x=10)
        ✅ "平移实体2，X5 Y0 Z3" → move_body(body_name="实体2", offset_x=5, offset_z=3)

        [Note]
        - Unit: mm
        - Positive offset = positive axis direction
        """
        payload: Dict[str, Any] = {
            "body_name": body_name,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "offset_z": offset_z,
        }

        return await handle_api_response(
            client,
            "/api/feature/move_body",
            payload,
            default_message=f"Moved body {body_name} (X:{offset_x}, Y:{offset_y}, Z:{offset_z}) mm",
            check_success=True,
        )

