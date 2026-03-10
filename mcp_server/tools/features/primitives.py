"""
基础实体创建工具。

包含：create_box, create_cylinder, create_sphere, create_entity_relative
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client
from mcp_server.tools.helpers import (
    EntityType,
    handle_api_response,
    normalize_entity_type,
    parse_box_dimensions,
    parse_offset,
    resolve_alias,
    validate_box_dimensions,
    validate_cylinder_params,
)

__all__ = ["register"]


def register(app: FastMCP, client: Fusion360Client) -> None:
    """注册基础实体创建工具。"""

    @app.tool()
    async def create_box(
        width: float,
        height: float,
        depth: float,
        center_x: float = 0.0,
        center_y: float = 0.0,
        center_z: float = 0.0,
        edge_names: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Create a new box entity in Fusion 360 (no sketch required).
        
        [Usage - When to Use]
        - User says "创建一个..." / "新建一个..." / "生成一个..." → use this tool
        - User says "创建一个长X宽X高X的长方体" WITHOUT mentioning existing entity or relative position
        - Creates new entity at absolute coordinates (default: origin 0,0,0)
        - This is the PRIMARY tool for creating boxes - use it unless user explicitly mentions relative positioning
        
        [CRITICAL - After Success]
        - ✅ If create_box succeeds, the task is COMPLETE
        - ✅ Do NOT call create_sketch, extrude, or create_entity_relative after create_box succeeds
        - ✅ create_box creates the box directly - no additional steps needed
        - ✅ Return success message to user immediately after create_box succeeds
        
        [Don't Use When - Common Mistakes]
        - ❌ User mentions: "在实体X上方/下方/旁边" / "相对于某个实体" / "实体1上方" / "实体2下方"
          → Use create_entity_relative instead
        - ❌ Modifying existing entities → use modify_body_dimensions
        - ❌ User wants to create box relative to another entity → use create_entity_relative
        - ❌ If create_box already succeeded in this turn → task is complete, don't call other tools
        
        [Parameter Mapping - Chinese Input] (Must follow strictly)
        User input → Parameter:
        "高度/高/厚度" → depth (Z-axis, vertical)
        "长度/长" → width (X-axis, horizontal)
        "宽度/宽" → height (Y-axis, horizontal)
        Note: No 'length' parameter! Map "长度" to width.
        Note: Use center_x, center_y, center_z (not location, x, y, z, name).
        
        [Required Params] (mm):
        - width: X-axis size (CN: "长度/长")
        - height: Y-axis size (CN: "宽度/宽")
        - depth: Z-axis size (CN: "高度/高/厚度")
        
        [Optional Params]:
        - center_x/y/z: Box center coordinates (default: 0.0)
        - edge_names: Edge naming dict, e.g. {"length": "a", "width": "b", "height": "h"}
        
        [Examples - Correct Usage]
        ✅ "创建一个高10mm长20mm宽20mm的长方体" → create_box(width=20, height=20, depth=10)
          → After success, return message to user. DO NOT call other tools.
        ✅ "高0.1mm,长50mm,宽50mm" → create_box(width=50, height=50, depth=0.1)
          → After success, return message to user. DO NOT call other tools.
        
        [Examples - Wrong Usage (Don't Use This Tool)]
        ❌ "在实体1上方创建一个长方体" → use create_entity_relative
        ❌ "相对于实体2创建一个长方体" → use create_entity_relative
        
        [Tech]
        - Coordinate: width=X, height=Y, depth=Z
        - Unit: mm
        - Creates box directly without sketch - no need for create_sketch or extrude
        - After successful call, task is COMPLETE - return success message, do NOT call other tools
        """
        payload: Dict[str, Any] = {
            "width": width,
            "height": height,
            "depth": depth,
            "center": {
                "x": center_x,
                "y": center_y,
                "z": center_z,
            },
        }
        
        if edge_names is not None:
            payload["edge_names"] = edge_names

        # 验证尺寸参数
        if width <= 0 or height <= 0 or depth <= 0:
            raise ValueError(
                f"长方体的尺寸必须大于 0。当前值: width={width}, height={height}, depth={depth}"
            )

        result = await handle_api_response(
            client,
            "/api/feature/create_box",
            payload,
            default_message=f"已成功创建长方体：长度 {width}mm（X轴），宽度 {height}mm（Y轴），高度 {depth}mm（Z轴）。任务已完成。",
            check_success=False,  # create_box 可能不返回 success 字段
        )
        # 确保返回消息明确表示任务已完成
        if "已完成" not in result and "成功" not in result:
            return f"{result} 任务已完成。"
        return result

    @app.tool()
    async def create_entity_relative(
        entity_type: Optional[str] = None,  # 必需参数，但允许通过 shape_type 提供
        shape_type: Optional[str] = None,  # 作为 entity_type 的别名
        direction: str = "above",
        distance: float = 0.0,
        base_body_name: Optional[str] = None,
        parent_body_name: Optional[str] = None,  # 作为 base_body_name 的别名
        offset_x: Optional[float] = None,
        offset_y: Optional[float] = None,
        offset_z: Optional[float] = None,
        # 支持列表格式的偏移量（如果提供，将覆盖 offset_x/y/z）
        offset: Optional[List[float]] = None,
        position_offset: Optional[List[float]] = None,  # 作为 offset 的别名
        # Box 参数
        width: Optional[float] = None,
        height: Optional[float] = None,
        depth: Optional[float] = None,
        # 支持列表或字典格式的尺寸（如果提供，将覆盖 width/height/depth）
        dimensions: Optional[Any] = None,  # 可以是 List[float] 或 Dict[str, float]
        size: Optional[Any] = None,  # 作为 dimensions 的别名
        # Cylinder 参数
        radius: Optional[float] = None,
        cylinder_height: Optional[float] = None,
        cylinder_axis: str = "Z",
    ) -> str:
        """
        Create new entity (box or cylinder) relative to existing entity.
        
        [Usage - When to Use]
        - User mentions: "在实体X上方/下方/旁边" / "相对于实体X" / "实体1上方" / "实体2下方" → use this tool
        - User explicitly mentions relative positioning to existing entity
        - This tool is ONLY for creating entities relative to existing entities
        - Base entity must already exist (get name from get_document_content)
        
        [IMPORTANT - When NOT to Use - Common Mistakes]
        - ❌ User says "创建一个长X宽X高X的长方体" WITHOUT mentioning existing entity or relative position
          → Use create_box instead (creating independent entity)
        - ❌ User says "创建一个圆柱体" WITHOUT mentioning "在...上方/下方/旁边"
          → Use create_cylinder instead (creating independent entity)
        - ❌ No base_body_name provided AND user doesn't mention relative positioning
          → Use create_box/create_cylinder instead
        - ❌ If create_box already succeeded in this turn → task is complete, don't call this tool
        
        [Required] entity_type or shape_type (MUST provide, cannot omit):
        - "长方体/立方体/box" or mentions "长/宽/高" → entity_type="box" or shape_type="box"
        - "圆柱体/cylinder" or mentions "半径/直径" → entity_type="cylinder" or shape_type="cylinder"
        - Aliases: entity_type ↔ shape_type (same param)
        
        [Parameter Aliases]
        - entity_type ↔ shape_type
        - offset ↔ position_offset
        - dimensions ↔ size
        - base_body_name ↔ parent_body_name
        
        [When to Use] (Must follow strictly)
        User mentions: "在实体X上方/下方/旁边/前方/后方/左侧/右侧" / "相对于某个实体" / "实体1上方" / "距离实体X中心左侧/右侧"
        → Use this tool, NOT create_box/create_cylinder
        
        [When NOT to Use] (Must follow strictly)
        User says: "创建一个长X宽X高X的长方体" (without mentioning existing entity or relative position)
        → Use create_box, NOT this tool
        User says: "创建一个圆柱体" (without mentioning existing entity or relative position)
        → Use create_cylinder, NOT this tool
        
        [Get Entity Name Steps] (Must follow strictly - CRITICAL!)
        When user mentions entity name (e.g., "实体1", "实体2", "立方体"):
        1. Call get_document_content ONCE to get entity list
        2. Find matching entity from results by checking "名称:" field
        3. Extract EXACT entity name from "名称: XXX" field
        4. Use exact entity name as base_body_name, call this tool immediately
        5. Don't call get_document_content again! Reuse the results.
        
        [Entity Name Matching - Important]
        - User says "实体1" → find entity with name containing "1" or first entity (from "名称: 实体1" or "名称: Body1" field)
        - User says "立方体" → find entity with name containing "立方体" or "Body" (from "名称:" field)
        - User says "第一个实体" → use first entity name from list
        - User says "最后一个实体" → omit base_body_name (uses last entity automatically)
        - ALWAYS extract exact name from get_document_content results, don't guess!
        
        [Common Mistakes]
        - ❌ Using guessed name like "立方体" without checking get_document_content → will fail
        - ❌ Not calling get_document_content before using entity name → will fail
        - ❌ Using wrong entity name format → must match exactly from "名称:" field
        
        [Parameter Mapping - Chinese Input] (For box, must follow strictly)
        User input → Parameter:
        "高度/高/厚度" → depth (Z-axis)
        "长度/长" → width (X-axis)
        "宽度/宽" → height (Y-axis)
        Note: No 'length' parameter! Map "长度" to width.
        
        [Required Params]
        - entity_type or shape_type: "box" or "cylinder" (MUST provide)
          * "长方体/立方体" or mentions "长/宽/高" → "box"
          * "圆柱体" or mentions "半径/直径" → "cylinder"
        
        [Optional Params]
        - direction: Relative direction (default: "above")
          Values: "above/top/+Z", "below/bottom/-Z", "front/+Y", "back/-Y", "right/+X", "left/-X"
        - distance: Distance between entity boundaries (mm, default: 0.0)
          Note: Boundary-to-boundary distance, not center-to-center
          Example: "上方5mm处" → distance=5.0
        - base_body_name or parent_body_name: Base entity name (optional, uses last entity if omitted)
        - offset_x/y/z: Additional offset (mm, default: 0.0)
          - offset_x: X-axis offset from base entity center (for horizontal alignment)
          - offset_y: Y-axis offset from base entity center (for vertical alignment)
          - offset_z: Additional offset along direction axis (for fine-tuning)
          Note: For "above" direction, offset_x/y adjust horizontal position, offset_z adjusts vertical position
        - offset or position_offset: Offset list [x, y, z] (overrides offset_x/y/z)
        
        [Position Calculation - Important]
        - "正上方" (directly above): direction="above", distance=0, offset_x=0, offset_y=0, offset_z=0
          → New entity center aligns with base entity center in X and Y
          → Z position: base_top_surface + new_height/2
          → New entity bottom surface touches base entity top surface (surface-to-surface distance = 0)
        - "上方x处" (x mm above): direction="above", distance=x, offset_x=0, offset_y=0, offset_z=0
          → New entity bottom surface is x mm above base entity top surface (surface-to-surface distance = x)
          → Z position: base_top_surface + distance + new_height/2
        - "上方x处，向右偏移y": direction="above", distance=x, offset_x=y, offset_y=0, offset_z=0
          → New entity is x mm above base entity top surface, shifted y mm to the right (X+ direction)
        
        [Calculation Formula for "above" direction - Surface Alignment]
        Uses surface-to-surface calculation (more intuitive than center-to-center):
        - new_center_x = base_center_x + offset_x
        - new_center_y = base_center_y + offset_y
        - new_center_z = base_top_surface + distance + new_height/2 + offset_z
        
        Where:
        - base_top_surface = bbox.maxPoint.z (base entity top surface Z coordinate)
        - distance = 0: New entity bottom surface touches base entity top surface
        - distance > 0: Surface-to-surface distance = distance (more intuitive)
        - This ensures "正上方" means directly above with surfaces touching
        
        [Box Params] (when entity_type="box", mm):
        - width: X-axis size (CN: "长度/长")
        - height: Y-axis size (CN: "宽度/宽")
        - depth: Z-axis size (CN: "高度/高/厚度")
        - dimensions or size: [width, height, depth] or {"width":w, "height":h, "depth":d} or {"length":l, "width":w, "height":h}
          Note: "length" in dict maps to width (X-axis)
        
        [Cylinder Params] (when entity_type="cylinder", mm):
        - radius: Cylinder radius (CN: "半径/直径的一半")
        - cylinder_height: Cylinder height (CN: "高度/高") - Note: param name is cylinder_height, not height!
        - cylinder_axis: Axis direction "X"/"Y"/"Z" (default: "Z")
        
        [How It Works]
        1. Get base entity bounding box (or use last entity)
        2. Calculate boundary position in direction (e.g., maxPoint.z for "above")
        3. Calculate new entity center:
           - Direction axis: boundary + distance + new_entity_size/2 + offset_axis
           - Other axes: base_center + offset (default: aligned with base center)
        4. Create entity at calculated position
        
        [Position Calculation Details]
        For "above" (+Z) direction:
        - X/Y axes: Aligned with base entity center by default (offset_x/y for adjustment)
        - Z axis: base_max_z + distance + new_depth/2 + offset_z
        This ensures "正上方" means directly above with center alignment
        
        [Examples]
        Ex1: "在实体1上方0mm处创建一个高1mm、长10mm、宽10mm的长方体"
          → Step 1: Call get_document_content ONCE
          → Step 2: Find entity from results, extract exact name from "名称: 实体1" or "名称: Body1" field
          → Step 3: create_entity_relative(entity_type="box", direction="above", width=10, height=10, depth=1, 
                                           distance=0, base_body_name="实体1")  # Use exact name from step 2
          → Mapping: 高1mm→depth=1, 长10mm→width=10, 宽10mm→height=10
          → CRITICAL: Must use exact name from get_document_content, not guessed name!
        
        Ex2: "在当前实体上方创建一个高5mm、长30mm、宽30mm的长方体，距离2mm"
          → create_entity_relative(entity_type="box", direction="above", width=30, height=30, depth=5, distance=2)
        
        Ex3: "在实体2左侧1mm处创建一个高0.8mm、半径0.5mm的圆柱体"
          → Call get_document_content ONCE, find "实体2"
          → create_entity_relative(entity_type="cylinder", base_body_name="实体2", direction="left", 
                                   distance=1.0, radius=0.5, cylinder_height=0.8)
        
        Ex4: Using dimensions list: dimensions=[0.01, 0.01, 0.01], offset=[0, 0, 0.001]
        Ex5: Using dimensions dict: dimensions={"length": 10, "width": 10, "height": 1}
          → Maps: length→width(X), width→height(Y), height→depth(Z)
        Ex6: Using aliases: shape_type="box", position_offset=[0,0,1], parent_body_name="实体1"
        
        [Tech]
        - Position = base_boundary + distance + size/2 + offset
        - Unit: mm
        """
        # 处理 entity_type/shape_type 别名并规范化
        final_entity_type = normalize_entity_type(entity_type, shape_type)
        
        # 处理 parent_body_name 别名
        final_base_body_name = resolve_alias(base_body_name, parent_body_name)
        
        # 处理 offset 参数
        final_offset_x, final_offset_y, final_offset_z = parse_offset(
            offset, position_offset, offset_x, offset_y, offset_z
        )
        
        # 处理 box 尺寸参数
        final_width, final_height, final_depth = parse_box_dimensions(
            width, height, depth, dimensions, size
        )
        
        payload: Dict[str, Any] = {
            "entity_type": final_entity_type,
            "direction": direction,
            "distance": distance,
            "offset_x": final_offset_x,
            "offset_y": final_offset_y,
            "offset_z": final_offset_z,
        }
        
        if final_base_body_name is not None:
            payload["base_body_name"] = final_base_body_name
        
        # 根据实体类型添加相应参数并验证
        if final_entity_type == EntityType.BOX.value:
            validate_box_dimensions(final_width, final_height, final_depth)
            payload["width"] = final_width
            payload["height"] = final_height
            payload["depth"] = final_depth
        elif final_entity_type == EntityType.CYLINDER.value:
            validate_cylinder_params(radius, cylinder_height)
            payload["radius"] = radius
            payload["cylinder_height"] = cylinder_height
            payload["cylinder_axis"] = cylinder_axis
        else:
            raise ValueError(f"不支持的实体类型: {final_entity_type}，支持的类型: {EntityType.BOX.value}/{EntityType.CYLINDER.value}")

        # 构建默认消息
        if final_entity_type == EntityType.BOX.value:
            entity_desc = f"{final_width}x{final_height}x{final_depth}"
        else:
            entity_desc = f"半径{radius}高度{cylinder_height}"
        default_msg = f"已在实体{direction}方向创建{entity_desc}的{final_entity_type}，距离 {distance}mm"
        
        return await handle_api_response(
            client,
            "/api/feature/create_entity_relative",
            payload,
            default_message=default_msg,
            check_success=True,
        )

    @app.tool()
    async def create_cylinder(
        radius: float,
        height: float,
        center_x: float = 0.0,
        center_y: float = 0.0,
        center_z: float = 0.0,
        axis: str = "Z",
    ) -> str:
        """
        Create cylinder in Fusion 360 (no sketch required).
        
        [Usage - When to Use]
        - User says "创建一个圆柱体" / "新建一个圆柱体" WITHOUT mentioning existing entity or relative position
        - Creates new entity at absolute coordinates (default: origin 0,0,0)
        - This is the PRIMARY tool for creating cylinders - use it unless user explicitly mentions relative positioning
        
        [Don't Use When - Common Mistakes]
        - ❌ User mentions: "在实体X上方/下方/旁边" / "相对于某个实体" / "实体1上方"
          → Use create_entity_relative with entity_type="cylinder" instead
        - ❌ Modifying existing entities → use modify_body_dimensions
        - ❌ If create_cylinder already succeeded in this turn → task is complete, don't call other tools
        
        [Required Params] (mm):
        - radius: Cylinder radius (CN: "半径/直径的一半")
        - height: Cylinder height (CN: "高度/高")
        
        [Optional Params]:
        - center_x/y/z: Cylinder center coordinates (default: 0.0)
        - axis: Axis direction "X"/"Y"/"Z" (default: "Z")
        
        [Examples - Correct Usage]
        ✅ "创建一个半径5mm高度10mm的圆柱体" → create_cylinder(radius=5, height=10)
        ✅ "创建一个圆柱体，半径10，高度20" → create_cylinder(radius=10, height=20)
        
        [Examples - Wrong Usage (Don't Use This Tool)]
        ❌ "在实体1上方创建一个圆柱体" → use create_entity_relative with entity_type="cylinder"
        ❌ "相对于实体2创建一个圆柱体" → use create_entity_relative with entity_type="cylinder"
        
        [Note]
        - Unit: mm
        - After successful call, task is complete - no need to call other tools
        """
        # 验证参数
        if radius <= 0 or height <= 0:
            raise ValueError(
                f"圆柱体的半径和高度必须大于 0。当前值: radius={radius}, height={height}"
            )

        payload: Dict[str, Any] = {
            "radius": radius,
            "height": height,
            "center": {
                "x": center_x,
                "y": center_y,
                "z": center_z,
            },
            "axis": axis,
        }

        return await handle_api_response(
            client,
            "/api/feature/create_cylinder",
            payload,
            default_message=f"已创建半径 {radius}、高度 {height} 的圆柱体",
            check_success=False,
        )

    @app.tool()
    async def create_sphere(
        radius: float,
        center_x: float = 0.0,
        center_y: float = 0.0,
        center_z: float = 0.0,
    ) -> str:
        """
        Create sphere in Fusion 360 (no sketch required).
        
        [Usage - When to Use]
        - User says "创建一个球体" / "新建一个球体" / "生成一个球体"
        - Creates new sphere at absolute coordinates (default: origin 0,0,0)
        - This is the ONLY tool for creating spheres (no relative positioning version)
        
        [Don't Use When]
        - ❌ Modifying existing entities → use modify_body_dimensions (if supported)
        - ❌ If create_sphere already succeeded in this turn → task is complete, don't call other tools
        
        [Required Params] (mm):
        - radius: Sphere radius (must be > 0, CN: "半径")
        
        [Optional Params]:
        - center_x/y/z: Sphere center coordinates (default: 0.0)
        
        [Examples]
        ✅ "创建一个半径10mm的球体" → create_sphere(radius=10)
        ✅ "创建一个球体，半径5" → create_sphere(radius=5)
        
        [Note]
        - Creates sphere directly, no sketch required
        - Unit: mm
        - After successful call, task is complete - no need to call other tools
        """
        # 验证参数
        if radius <= 0:
            raise ValueError(f"球体的半径必须大于 0。当前值: radius={radius}")

        payload: Dict[str, Any] = {
            "radius": radius,
            "center": {
                "x": center_x,
                "y": center_y,
                "z": center_z,
            },
        }

        return await handle_api_response(
            client,
            "/api/feature/create_sphere",
            payload,
            default_message=f"已创建半径 {radius} 的球体",
            check_success=False,
        )

