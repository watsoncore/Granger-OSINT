"""QA-only compositor capture, restricted to an unobscured owned application."""
import ctypes
from ctypes import wintypes as W
import os
from PySide6.QtGui import QImage


def capture_owned_background(pet,roi=None):
    user=ctypes.WinDLL('user32');gdi=ctypes.WinDLL('gdi32');pid=os.getpid()
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.GetForegroundWindow.restype=W.HWND
    user.GetWindowRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
    user.GetClientRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
    user.ClientToScreen.argtypes=[W.HWND,ctypes.POINTER(W.POINT)]
    user.IsWindowVisible.argtypes=[W.HWND];user.IsIconic.argtypes=[W.HWND]
    background=int(pet.panel.winId())
    renderer=pet.panel.desktop_surface.trusted_page.renderProcessPid() if pet.panel.desktop_surface else 0
    owned_pids={pid,int(renderer)}
    dwm=ctypes.WinDLL('dwmapi');dwm.DwmGetWindowAttribute.argtypes=[W.HWND,W.DWORD,ctypes.c_void_p,W.DWORD]
    def cloaked(hwnd):
        value=W.DWORD();return dwm.DwmGetWindowAttribute(hwnd,14,ctypes.byref(value),ctypes.sizeof(value))==0 and bool(value.value)
    def owner(hwnd):
        value=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(value));return value.value
    if owner(background)!=pid or not user.IsWindowVisible(background) or user.IsIconic(background):return None,'background_hidden'
    client=W.RECT();user.GetClientRect(background,ctypes.byref(client));origin=W.POINT()
    user.ClientToScreen(background,ctypes.byref(origin))
    client=(origin.x,origin.y,origin.x+client.right,origin.y+client.bottom)
    if roi is None:
        bounds=W.RECT();target=pet.cameo if pet.cameo and pet.cameo.isVisible() else pet
        user.GetWindowRect(int(target.winId()),ctypes.byref(bounds))
        roi=(max(client[0],bounds.left-180),max(client[1],bounds.top-60),
            min(client[2],bounds.right+12),min(client[3],bounds.bottom+24))
        pet._qa_native_geometry={'client_physical':client,'stage_physical':[bounds.left,bounds.top,bounds.right,bounds.bottom],
            'stage_qt':list(target.frameGeometry().getRect()),'pet_qt':list(pet.frameGeometry().getRect()),
            'panel_qt':list(pet.panel.frameGeometry().getRect()),'dock_qt':list(pet._dock_bounds.getRect()) if pet._dock_bounds else [],
            'dpr':pet.devicePixelRatioF()}
    if roi[0]<client[0] or roi[1]<client[1] or roi[2]>client[2] or roi[3]>client[3] or roi[2]<=roi[0] or roi[3]<=roi[1]:return None,'crop_outside_owned_client'
    callback_type=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    user.EnumWindows.argtypes=[callback_type,W.LPARAM]
    def unobscured():
        found=[False];covered=[False]
        @callback_type
        def visit(hwnd,_):
            if hwnd==background:found[0]=True;return False
            if owner(hwnd) not in owned_pids and user.IsWindowVisible(hwnd) and not user.IsIconic(hwnd) and not cloaked(hwnd):
                box=W.RECT();user.GetWindowRect(hwnd,ctypes.byref(box))
                if max(box.left,roi[0])<min(box.right,roi[2]) and max(box.top,roi[1])<min(box.bottom,roi[3]):covered[0]=True;return False
            return True
        user.EnumWindows(visit,0);return found[0] and not covered[0]
    if not unobscured():return None,'foreign_occlusion'
    user.GetDC.argtypes=[W.HWND];user.GetDC.restype=W.HDC;user.ReleaseDC.argtypes=[W.HWND,W.HDC]
    gdi.CreateCompatibleDC.argtypes=[W.HDC];gdi.CreateCompatibleDC.restype=W.HDC
    gdi.CreateCompatibleBitmap.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=W.HBITMAP
    gdi.SelectObject.argtypes=[W.HDC,W.HGDIOBJ];gdi.SelectObject.restype=W.HGDIOBJ
    gdi.DeleteObject.argtypes=[W.HGDIOBJ];gdi.DeleteDC.argtypes=[W.HDC]
    gdi.BitBlt.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.HDC,ctypes.c_int,ctypes.c_int,W.DWORD]
    class Header(ctypes.Structure):
        _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bits',W.WORD),
            ('compression',W.DWORD),('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]
    gdi.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,ctypes.c_void_p,ctypes.POINTER(Header),W.UINT]
    width,height=roi[2]-roi[0],roi[3]-roi[1];screen=user.GetDC(0);dc=gdi.CreateCompatibleDC(screen)
    bitmap=gdi.CreateCompatibleBitmap(screen,width,height);old=gdi.SelectObject(dc,bitmap)
    try:
        if not gdi.BitBlt(dc,0,0,width,height,screen,roi[0],roi[1],0x40CC0020):return None,'bitblt_failed'
        header=Header(ctypes.sizeof(Header),width,-height,1,32,0,width*height*4,0,0,0,0)
        buffer=ctypes.create_string_buffer(width*height*4)
        if not gdi.GetDIBits(dc,bitmap,0,height,buffer,ctypes.byref(header),0):return None,'dib_failed'
        if not unobscured():return None,'occlusion_changed_during_capture'
        image=QImage(buffer.raw,width,height,width*4,QImage.Format.Format_RGB32).copy()
        return (image,roi),''
    finally:
        gdi.SelectObject(dc,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(dc);user.ReleaseDC(0,screen)
