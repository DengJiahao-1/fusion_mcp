"""
Other operations: fillet, chamfer, shell, combine, delete_body.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from mcp_server.clients import Fusion360Client
from mcp_server.tools.helpers import handle_api_response

__all__ = ["register"]


def register(app: FastMCP, client: Fusion360Client) -> None:
    """Register other operation tools."""

    @app.tool()
    async def fillet(
        body_name: str,
        radius: float,
        edge_indices: Optional[List[int]] = None,
    ) -> str:
        """
        Apply fillet (rounded corner) to edges of existing entity.
        
        [Usage - When to Use]
        - User says "add fillet" / "round corners" / "fillet edges" → use this tool
        - Applies rounded corners to edges of EXISTING entity
        - Entity must already exist, requires exact entity name (from get_document_content)
        
        [Don't Use When]
        - ❌ Entity doesn't exist yet → first create entity with create_box/create_cylinder
        - ❌ User wants to create new entity → use create_box/create_cylinder instead
        
        [Required Params]:
        - body_name: Entity name (must exist, get from get_document_content)
        - radius: Fillet radius (must be > 0)
        
        [Optional Params]:
        - edge_indices: List of edge indices to fillet (if omitted, fillets all edges)
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions "Body1" / "Body2":
        1. Call get_document_content ONCE
        2. Find matching entity name (check "Name:" field)
        3. Use exact name as body_name
        4. Don't call get_document_content again! Reuse the results.
        
        [Examples]
        fillet(body_name="Body1", radius=5)
        
        [Note]
        - Modifies existing entity, not creates new one
        - Unit: mm
        """
        if radius <= 0:
            raise ValueError(f"Fillet radius must be > 0. Got: {radius}")

        payload: Dict[str, Any] = {
            "body_name": body_name,
            "radius": radius,
            "edge_indices": edge_indices,
        }

        return await handle_api_response(
            client,
            "/api/feature/fillet",
            payload,
            default_message=f"Fillet applied to {body_name}",
            check_success=False,
        )

    @app.tool()
    async def chamfer(
        body_name: str,
        distance: float,
        edge_indices: Optional[List[int]] = None,
    ) -> str:
        """
        Apply chamfer (beveled corner) to edges of existing entity.
        
        [Usage - When to Use]
        - User says "add chamfer" / "chamfer edges" → use this tool
        - Applies beveled corners to edges of EXISTING entity
        - Entity must already exist, requires exact entity name (from get_document_content)
        
        [Don't Use When]
        - ❌ Entity doesn't exist yet → first create entity with create_box/create_cylinder
        - ❌ User wants to create new entity → use create_box/create_cylinder instead
        
        [Required Params]:
        - body_name: Entity name (must exist, get from get_document_content)
        - distance: Chamfer distance (must be > 0)
        
        [Optional Params]:
        - edge_indices: List of edge indices to chamfer (if omitted, chamfers all edges)
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions "Body1" / "Body2":
        1. Call get_document_content ONCE
        2. Find matching entity name (check "Name:" field)
        3. Use exact name as body_name
        4. Don't call get_document_content again! Reuse the results.
        
        [Examples]
        chamfer(body_name="Body1", distance=3)
        
        [Note]
        - Modifies existing entity, not creates new one
        - Unit: mm
        """
        if distance <= 0:
            raise ValueError(f"Chamfer distance must be > 0. Got: {distance}")

        payload: Dict[str, Any] = {
            "body_name": body_name,
            "distance": distance,
            "edge_indices": edge_indices,
        }

        return await handle_api_response(
            client,
            "/api/feature/chamfer",
            payload,
            default_message=f"Chamfer applied to {body_name}",
            check_success=False,
        )

    @app.tool()
    async def shell(
        body_name: str,
        thickness: float,
        face_indices: Optional[List[int]] = None,
    ) -> str:
        """
        Shell existing entity to create thin-walled structure (hollow inside).
        
        [Usage - When to Use]
        - User says "shell" / "hollow" / "thin wall" → use this tool
        - Creates hollow structure from solid entity
        - Entity must already exist, requires exact entity name (from get_document_content)
        
        [Don't Use When]
        - ❌ Entity doesn't exist yet → first create entity with create_box/create_cylinder
        - ❌ User wants to create new solid entity → use create_box/create_cylinder instead
        
        [Required Params]:
        - body_name: Entity name (must exist, get from get_document_content)
        - thickness: Wall thickness (must be > 0)
        
        [Optional Params]:
        - face_indices: List of face indices to remove (openings, if omitted creates closed shell)
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions "Body1" / "Body2":
        1. Call get_document_content ONCE
        2. Find matching entity name (check "Name:" field)
        3. Use exact name as body_name
        4. Don't call get_document_content again! Reuse the results.
        
        [Examples]
        shell(body_name="Body1", thickness=2)
        
        [Note]
        - Modifies existing entity, not creates new one
        - Creates hollow structure with specified wall thickness
        - Unit: mm
        - Shell thickness cannot be changed after; use undo and re-shell. modify_body_dimensions cannot change shell thickness.
        """
        if thickness <= 0:
            raise ValueError(f"Shell thickness must be > 0. Got: {thickness}")

        payload: Dict[str, Any] = {
            "body_name": body_name,
            "thickness": thickness,
            "face_indices": face_indices,
        }

        return await handle_api_response(
            client,
            "/api/feature/shell",
            payload,
            default_message=f"Shell applied to {body_name}",
            check_success=False,
        )

    @app.tool()
    async def combine(
        target_body: str,
        tool_bodies: List[str],
        operation: str = "Cut",
        keep_tools: bool = False,
    ) -> str:
        """
        Perform boolean operations on existing entities (merge, cut, intersect).
        
        [Usage - When to Use]
        - User says "merge bodies" / "body1 subtract body2" / "intersect" → use this tool
        - Performs boolean operations (union, subtraction, intersection) on EXISTING entities
        - All entities must already exist, requires exact entity names (from get_document_content)
        
        [Don't Use When]
        - ❌ Entities don't exist yet → first create entities with create_box/create_cylinder
        - ❌ User wants to create new entity → use create_box/create_cylinder instead
        
        [Required Params]:
        - target_body: Target entity name (must exist, get from get_document_content)
        - tool_bodies: List of tool entity names (must exist, get from get_document_content)
          → Example: ["Body1", "Body2"]
        
        [Optional Params]:
        - operation: Boolean operation type (default: "Cut")
          Values: "Cut" (subtract), "Join"/"Merge" (merge), "Intersect" (intersection)
        - keep_tools: Keep tool entities after operation (default: False)
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions "Body1" / "Body2":
        1. Call get_document_content ONCE
        2. Find matching entity names (check "Name:" field)
        3. Use exact names for target_body and tool_bodies
        4. Don't call get_document_content again! Reuse the results.
        
        [Examples]
        combine(target_body="Body1", tool_bodies=["Body2"], operation="Cut")
        combine(target_body="Body1", tool_bodies=["Body2"], operation="Join")
        
        [Note]
        - Performs boolean operations on existing entities, not creates new ones
        - Create entities first with create_box/create_cylinder, then use this tool
        - Unit: mm
        """
        payload: Dict[str, Any] = {
            "target_body": target_body,
            "tool_bodies": tool_bodies,
            "operation": operation,
            "keep_tools": keep_tools,
        }

        return await handle_api_response(
            client,
            "/api/feature/combine",
            payload,
            default_message=f"Boolean {operation} completed",
            check_success=False,
        )

    @app.tool()
    async def delete_body(body_name: str) -> str:
        """
        Delete specified entity.
        
        [Get Entity Name Steps] (Must follow strictly)
        When user mentions "Body1" / "Body2":
        1. Call get_document_content ONCE to get entity list
        2. Find matching entity from results
        3. Use exact entity name as body_name, call this tool immediately
        4. Don't call get_document_content again! Reuse the results.
        
        [Required Params]
        - body_name: Entity name to delete (must exist)
        
        [Name Matching]
        - User says "Body1" → find name containing "1" or index 1 (from "Name: Body1" field)
        - User says "first entity" → use index 1
        - User says "last entity" → use last entity
        
        [Examples]
        delete_body(body_name="Body1")
        Ex2: Delete "Box1" → delete_body(body_name="Box1")
        
        [Note]
        - Deletion is irreversible
        - If entity doesn't exist, throws error
        - Entity will be permanently removed from document
        """
        if not body_name or not body_name.strip():
            raise ValueError("body_name cannot be empty")
        
        payload: Dict[str, Any] = {
            "body_name": body_name.strip(),
        }

        return await handle_api_response(
            client,
            "/api/feature/delete_body",
            payload,
            default_message=f"Body '{body_name}' deleted",
            check_success=True,
        )

