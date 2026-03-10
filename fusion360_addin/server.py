"""
HTTP 服务器模块

在 Fusion 360 内运行 HTTP 服务器，接收来自 MCP 服务器的请求。
"""

import threading
import traceback
from typing import Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse

try:
    import adsk.core
    import adsk.fusion
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False

from .logger import get_default_logger

logger = get_default_logger()


class APIRequestHandler(BaseHTTPRequestHandler):
    """处理 API 请求的 HTTP 请求处理器"""
    
    def log_message(self, format, *args):
        """重写日志方法，使用统一的日志系统"""
        message = format % args
        logger.info(f"HTTP请求: {message}")
    
    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """处理 GET 请求"""
        try:
            if self.path == '/api/document/info':
                response = self._handle_get_document_info()
            elif self.path == '/api/document/content':
                response = self._handle_get_document_content()
            else:
                response = {'error': f'未知的端点: {self.path}'}
                self.send_response(404)
            
            self._send_json_response(response)
        except Exception as e:
            self._send_error_response(str(e))
    
    def do_POST(self):
        """处理 POST 请求"""
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8')) if body else {}
            
            # 路由到相应的处理函数
            if self.path == '/api/sketch/create':
                response = self._handle_create_sketch(data)
            elif self.path == '/api/sketch/create_offset':
                response = self._handle_create_sketch_offset(data)
            elif self.path == '/api/sketch/delete':
                response = self._handle_delete_sketch(data)
            elif self.path == '/api/sketch/line':
                response = self._handle_sketch_line(data)
            elif self.path == '/api/sketch/rectangle':
                response = self._handle_sketch_rectangle(data)
            elif self.path == '/api/sketch/rectangle_corners':
                response = self._handle_sketch_rectangle_corners(data)
            elif self.path == '/api/sketch/circle':
                response = self._handle_sketch_circle(data)
            elif self.path == '/api/sketch/arc':
                response = self._handle_sketch_arc(data)
            elif self.path == '/api/sketch/polyline':
                response = self._handle_sketch_polyline(data)
            elif self.path == '/api/sketch/helix':
                response = self._handle_sketch_helix(data)
            elif self.path == '/api/feature/create_box':
                response = self._handle_create_box(data)
            elif self.path == '/api/feature/create_entity_relative':
                response = self._handle_create_entity_relative(data)
            elif self.path == '/api/feature/create_cylinder':
                response = self._handle_create_cylinder(data)
            elif self.path == '/api/feature/create_sphere':
                response = self._handle_create_sphere(data)
            elif self.path == '/api/feature/extrude':
                response = self._handle_extrude(data)
            elif self.path == '/api/feature/revolve':
                response = self._handle_revolve(data)
            elif self.path == '/api/feature/sweep':
                response = self._handle_sweep(data)
            elif self.path == '/api/feature/loft':
                response = self._handle_loft(data)
            elif self.path == '/api/feature/fillet':
                response = self._handle_fillet(data)
            elif self.path == '/api/feature/chamfer':
                response = self._handle_chamfer(data)
            elif self.path == '/api/feature/shell':
                response = self._handle_shell(data)
            elif self.path == '/api/feature/combine':
                response = self._handle_combine(data)
            elif self.path == '/api/feature/rotate_body':
                response = self._handle_rotate_body(data)
            elif self.path == '/api/feature/move_body':
                response = self._handle_move_body(data)
            elif self.path == '/api/feature/modify_body_dimensions':
                response = self._handle_modify_body_dimensions(data)
            elif self.path == '/api/feature/delete_body':
                response = self._handle_delete_body(data)
            elif self.path == '/api/export/step':
                response = self._handle_export_step(data)
            elif self.path == '/api/export/iges':
                response = self._handle_export_iges(data)
            elif self.path == '/api/export/stl':
                response = self._handle_export_stl(data)
            else:
                response = {'error': f'未知的端点: {self.path}'}
                self.send_response(404)
            
            self._send_json_response(response)
        except Exception as e:
            self._send_error_response(str(e))
    
    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
        """发送 JSON 响应"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response_json = json.dumps(data, ensure_ascii=False)
        self.wfile.write(response_json.encode('utf-8'))
    
    def _send_error_response(self, error_message: str, status_code: int = 500):
        """发送错误响应"""
        response = {
            'error': error_message,
            'success': False
        }
        self._send_json_response(response, status_code)
    
    def _handle_get_document_info(self) -> Dict[str, Any]:
        """处理获取文档信息的请求"""
        try:
            app = adsk.core.Application.get()
            # 通过 activeProduct 获取 Design
            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                return {
                    'error': '没有活动的 Fusion 360 文档',
                    'success': False
                }

            doc = app.activeDocument
            name = doc.name if doc else 'Unknown'
            data_file = getattr(doc, 'dataFile', None) if doc else None
            # Fusion DataFile 没有 path 属性，使用 name 作为可显示信息
            path = (getattr(data_file, 'name', None) or '未保存')

            # 将单位枚举值转换为字符串
            units_enum = design.unitsManager.defaultLengthUnits
            # 单位枚举值通常是 adsk.core.UnitsLength 类型，转换为可读字符串
            units_str = "Unknown"
            if units_enum:
                # 尝试直接比较枚举值
                try:
                    if units_enum == adsk.core.UnitsLength.MillimeterUnits:
                        units_str = "mm"
                    elif units_enum == adsk.core.UnitsLength.CentimeterUnits:
                        units_str = "cm"
                    elif units_enum == adsk.core.UnitsLength.MeterUnits:
                        units_str = "m"
                    elif units_enum == adsk.core.UnitsLength.InchUnits:
                        units_str = "in"
                    elif units_enum == adsk.core.UnitsLength.FootUnits:
                        units_str = "ft"
                    else:
                        # 如果直接比较失败，尝试从字符串中提取
                        units_str_repr = str(units_enum)
                        if "Millimeter" in units_str_repr:
                            units_str = "mm"
                        elif "Centimeter" in units_str_repr:
                            units_str = "cm"
                        elif "Meter" in units_str_repr:
                            units_str = "m"
                        elif "Inch" in units_str_repr:
                            units_str = "in"
                        elif "Foot" in units_str_repr:
                            units_str = "ft"
                        else:
                            units_str = units_str_repr
                except (AttributeError, TypeError):
                    # 如果无法比较，尝试转换为字符串
                    units_str = str(units_enum) if units_enum else "Unknown"
            
            return {
                'name': name,
                'path': path,
                'units': units_str,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'获取文档信息失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_get_document_content(self) -> Dict[str, Any]:
        """处理获取文档详细内容的请求"""
        try:
            from . import feature_operations
            content = feature_operations.get_document_content()
            return {
                **content,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'获取文档内容失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_create_sketch(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建草图的请求"""
        try:
            from . import sketch_operations
            result = sketch_operations.create_sketch(
                plane=data.get('plane', 'XY'),
                name=data.get('name')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'创建草图失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_create_sketch_offset(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create offset sketch request"""
        try:
            from . import sketch_operations
            result = sketch_operations.create_sketch_offset(
                plane=data.get('plane', 'XY'),
                offset=data.get('offset', 0.0),
                name=data.get('name'),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create offset sketch failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_delete_sketch(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理删除草图的请求"""
        try:
            from . import sketch_operations
            result = sketch_operations.delete_sketch(
                sketch_name=data.get('sketch_name')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'删除草图失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_line(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sketch line request"""
        try:
            from . import sketch_operations
            result = sketch_operations.add_line(
                sketch_name=data.get('sketch_name'),
                x1=data.get('x1'),
                y1=data.get('y1'),
                x2=data.get('x2'),
                y2=data.get('y2'),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create line failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_rectangle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle rectangle by center request"""
        try:
            from . import sketch_operations
            result = sketch_operations.add_rectangle_by_center(
                sketch_name=data.get('sketch_name'),
                center_x=data.get('center_x'),
                center_y=data.get('center_y'),
                width=data.get('width'),
                height=data.get('height'),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create rectangle failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_rectangle_corners(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle rectangle by corners request"""
        try:
            from . import sketch_operations
            result = sketch_operations.add_rectangle_by_corners(
                sketch_name=data.get('sketch_name'),
                x1=data.get('x1'),
                y1=data.get('y1'),
                x2=data.get('x2'),
                y2=data.get('y2'),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create rectangle failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_circle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle circle request"""
        try:
            from . import sketch_operations
            result = sketch_operations.add_circle(
                sketch_name=data.get('sketch_name'),
                center_x=data.get('center_x'),
                center_y=data.get('center_y'),
                radius=data.get('radius'),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create circle failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_arc(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle arc request"""
        try:
            from . import sketch_operations
            result = sketch_operations.add_arc_3pt(
                sketch_name=data.get('sketch_name'),
                x1=data.get('x1'),
                y1=data.get('y1'),
                x2=data.get('x2'),
                y2=data.get('y2'),
                x3=data.get('x3'),
                y3=data.get('y3'),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create arc failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_polyline(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle polyline request"""
        try:
            from . import sketch_operations
            result = sketch_operations.add_polyline(
                sketch_name=data.get('sketch_name'),
                points=data.get('points') or [],
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create polyline failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sketch_helix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle helix sketch request"""
        try:
            from . import sketch_operations
            result = sketch_operations.create_helix_sketch(
                name=data.get('name'),
                center_x=data.get('center_x', 0.0),
                center_y=data.get('center_y', 0.0),
                center_z=data.get('center_z', 0.0),
                radius=data.get('radius'),
                height=data.get('height'),
                turns=data.get('turns'),
                points_per_turn=data.get('points_per_turn', 32),
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'Create helix failed: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_create_box(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建立方体的请求"""
        try:
            from . import feature_operations
            center = data.get('center', {})
            result = feature_operations.create_box(
                width=data.get('width'),
                height=data.get('height'),
                depth=data.get('depth'),
                center_x=center.get('x', 0.0),
                center_y=center.get('y', 0.0),
                center_z=center.get('z', 0.0),
                edge_names=data.get('edge_names')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'创建立方体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_create_entity_relative(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理在实体相对位置创建新实体的请求"""
        try:
            from . import feature_operations
            result = feature_operations.create_entity_relative(
                entity_type=data.get('entity_type'),
                base_body_name=data.get('base_body_name'),
                direction=data.get('direction', 'above'),
                distance=data.get('distance', 0.0),
                offset_x=data.get('offset_x', 0.0),
                offset_y=data.get('offset_y', 0.0),
                offset_z=data.get('offset_z', 0.0),
                # Box 参数
                width=data.get('width'),
                height=data.get('height'),
                depth=data.get('depth'),
                # Cylinder 参数
                radius=data.get('radius'),
                cylinder_height=data.get('cylinder_height'),
                cylinder_axis=data.get('cylinder_axis', 'Z')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'在实体相对位置创建新实体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_create_cylinder(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建圆柱体的请求"""
        try:
            from . import feature_operations
            center = data.get('center', {})
            result = feature_operations.create_cylinder(
                radius=data.get('radius'),
                height=data.get('height'),
                center_x=center.get('x', 0.0),
                center_y=center.get('y', 0.0),
                center_z=center.get('z', 0.0),
                axis=data.get('axis', 'Z')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'创建圆柱体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_create_sphere(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建球体的请求"""
        try:
            from . import feature_operations
            center = data.get('center', {})
            result = feature_operations.create_sphere(
                radius=data.get('radius'),
                center_x=center.get('x', 0.0),
                center_y=center.get('y', 0.0),
                center_z=center.get('z', 0.0)
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'创建球体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_extrude(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理拉伸操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.extrude(
                profile_name=data.get('profile_name'),
                distance=data.get('distance'),
                direction=data.get('direction', 'Normal'),
                operation=data.get('operation')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'拉伸操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_revolve(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理旋转操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.revolve(
                profile_name=data.get('profile_name'),
                axis=data.get('axis', 'Z'),
                angle_degrees=data.get('angle_degrees', 360.0),
                operation=data.get('operation')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'旋转操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_sweep(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理扫掠操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.sweep(
                profile_name=data.get('profile_name'),
                path_sketch=data.get('path_sketch'),
                operation=data.get('operation')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'扫掠操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_loft(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理放样操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.loft(
                section_profiles=data.get('section_profiles') or [],
                operation=data.get('operation')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'放样操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_fillet(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理圆角操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.fillet(
                body_name=data.get('body_name'),
                radius=data.get('radius'),
                edge_indices=data.get('edge_indices')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'圆角操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_chamfer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理倒角操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.chamfer(
                body_name=data.get('body_name'),
                distance=data.get('distance'),
                edge_indices=data.get('edge_indices')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'倒角操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_shell(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理抽壳操作的请求"""
        try:
            from . import feature_operations
            result = feature_operations.shell(
                body_name=data.get('body_name'),
                thickness=data.get('thickness'),
                face_indices=data.get('face_indices')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'抽壳操作失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_combine(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理布尔运算的请求"""
        try:
            from . import feature_operations
            result = feature_operations.combine(
                target_body=data.get('target_body'),
                tool_bodies=data.get('tool_bodies') or [],
                operation=data.get('operation', 'Cut'),
                keep_tools=data.get('keep_tools', False)
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'布尔运算失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_rotate_body(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理旋转实体的请求"""
        try:
            from . import feature_operations
            result = feature_operations.rotate_body(
                body_name=data.get('body_name'),
                angle_degrees=data.get('angle_degrees'),
                axis=data.get('axis', 'Z'),
                center_x=data.get('center_x', 0.0),
                center_y=data.get('center_y', 0.0),
                center_z=data.get('center_z', 0.0)
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'旋转实体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_move_body(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理移动实体的请求"""
        try:
            from . import feature_operations
            result = feature_operations.move_body(
                body_name=data.get('body_name'),
                offset_x=float(data.get('offset_x', 0.0)),
                offset_y=float(data.get('offset_y', 0.0)),
                offset_z=float(data.get('offset_z', 0.0))
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'移动实体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_modify_body_dimensions(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理修改实体维度的请求"""
        try:
            from . import feature_operations
            result = feature_operations.modify_body_dimensions(
                body_name=data.get('body_name'),
                entity_type=data.get('entity_type'),
                # Box 参数
                width=data.get('width'),
                height=data.get('height'),
                depth=data.get('depth'),
                # Cylinder 参数
                radius=data.get('radius'),
                cylinder_height=data.get('cylinder_height'),
                cylinder_axis=data.get('cylinder_axis', 'Z')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'修改实体维度失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }
    
    def _handle_delete_body(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理删除实体的请求"""
        try:
            from . import feature_operations
            result = feature_operations.delete_body(
                body_name=data.get('body_name')
            )
            return {
                'message': result,
                'success': True
            }
        except Exception as e:
            return {
                'error': f'删除实体失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_export_step(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理 STEP 导出请求"""
        try:
            from . import export_operations
            file_path = data.get('file_path')
            if not file_path or not str(file_path).strip():
                return {'error': '缺少 file_path 参数', 'success': False}
            result = export_operations.export_to_step(
                file_path=str(file_path).strip(),
                include_hidden=bool(data.get('include_hidden', False)),
            )
            return result
        except Exception as e:
            return {
                'error': f'STEP 导出失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_export_iges(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理 IGES 导出请求"""
        try:
            from . import export_operations
            file_path = data.get('file_path')
            if not file_path or not str(file_path).strip():
                return {'error': '缺少 file_path 参数', 'success': False}
            result = export_operations.export_to_iges(
                file_path=str(file_path).strip(),
                include_hidden=bool(data.get('include_hidden', False)),
            )
            return result
        except Exception as e:
            return {
                'error': f'IGES 导出失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }

    def _handle_export_stl(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理 STL 导出请求"""
        try:
            from . import export_operations
            file_path = data.get('file_path')
            if not file_path or not str(file_path).strip():
                return {'error': '缺少 file_path 参数', 'success': False}
            result = export_operations.export_to_stl(
                file_path=str(file_path).strip(),
                include_hidden=bool(data.get('include_hidden', False)),
                mesh_refinement=data.get('mesh_refinement'),
            )
            return result
        except Exception as e:
            return {
                'error': f'STL 导出失败: {str(e)}',
                'success': False,
                'traceback': traceback.format_exc()
            }


class HTTPServerThread(threading.Thread):
    """在后台线程中运行 HTTP 服务器"""
    
    def __init__(self, port: int = 9000):
        super().__init__(daemon=True)
        self.port = port
        self.server = None
        self.running = False
    
    def run(self):
        """启动 HTTP 服务器"""
        try:
            server_address = ('localhost', self.port)
            self.server = HTTPServer(server_address, APIRequestHandler)
            self.running = True
            
            # 通知 Fusion 360 服务器已启动
            logger.info(f'MCP HTTP 服务器已启动，监听端口 {self.port}')
            
            self.server.serve_forever()
        except Exception as e:
            error_msg = f'启动 HTTP 服务器失败: {str(e)}'
            logger.error(error_msg, exc_info=True)
            self.running = False
    
    def stop(self):
        """停止 HTTP 服务器"""
        if self.server:
            self.server.shutdown()
            self.running = False


# 全局服务器实例
_server_thread: Optional[HTTPServerThread] = None


def start_server(port: int = 9000):
    """启动 HTTP 服务器"""
    global _server_thread
    
    if _server_thread and _server_thread.running:
        return _server_thread
    
    _server_thread = HTTPServerThread(port)
    _server_thread.start()
    return _server_thread


def stop_server():
    """停止 HTTP 服务器"""
    global _server_thread
    
    if _server_thread:
        _server_thread.stop()
        _server_thread = None

