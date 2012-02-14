// Copyright (c) 2011 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/window_snapshot/window_snapshot.h"

#include "base/win/scoped_gdi_object.h"
#include "base/win/scoped_hdc.h"
#include "base/win/scoped_select_object.h"
#include "ui/gfx/codec/png_codec.h"
#include "ui/gfx/gdi_util.h"
#include "ui/gfx/rect.h"
#include "ui/gfx/size.h"

namespace {

gfx::Rect GetWindowBounds(gfx::NativeWindow window_handle) {
  RECT content_rect = {0, 0, 0, 0};
  ::GetWindowRect(window_handle, &content_rect);
  content_rect.right++;  // Match what PrintWindow wants.

  return gfx::Rect(content_rect.right - content_rect.left,
                   content_rect.bottom - content_rect.top);
}

} // namespace

namespace browser {

bool GrabWindowSnapshot(gfx::NativeWindow window_handle,
                        std::vector<unsigned char>* png_representation,
                        const gfx::Rect& snapshot_bounds) {
  DCHECK(snapshot_bounds.right() <= GetWindowBounds(window_handle).right());
  DCHECK(snapshot_bounds.bottom() <= GetWindowBounds(window_handle).bottom());

  // Create a memory DC that's compatible with the window.
  HDC window_hdc = GetWindowDC(window_handle);
  base::win::ScopedCreateDC mem_hdc(CreateCompatibleDC(window_hdc));

  BITMAPINFOHEADER hdr;
  gfx::CreateBitmapHeader(snapshot_bounds.width(),
                          snapshot_bounds.height(),
                          &hdr);
  unsigned char *bit_ptr = NULL;
  base::win::ScopedBitmap bitmap(
      CreateDIBSection(mem_hdc.get(),
                       reinterpret_cast<BITMAPINFO*>(&hdr),
                       DIB_RGB_COLORS,
                       reinterpret_cast<void **>(&bit_ptr),
                       NULL, 0));

  base::win::ScopedSelectObject select_bitmap(mem_hdc.get(), bitmap);
  // Clear the bitmap to white (so that rounded corners on windows
  // show up on a white background, and strangely-shaped windows
  // look reasonable). Not capturing an alpha mask saves a
  // bit of space.
  PatBlt(mem_hdc.get(), 0, 0, snapshot_bounds.width(), snapshot_bounds.height(),
         WHITENESS);

  if (snapshot_bounds.origin() != gfx::Point()) {
    BitBlt(mem_hdc.get(),
           0, 0, snapshot_bounds.width(), snapshot_bounds.height(),
           window_hdc,
           snapshot_bounds.x(), snapshot_bounds.y(),
           SRCCOPY);
  } else if (!PrintWindow(window_handle, mem_hdc.get(), 0)) {
    NOTREACHED();
  }

  // We now have a copy of the window contents in a DIB, so
  // encode it into a useful format for posting to the bug report
  // server.
  gfx::PNGCodec::Encode(bit_ptr, gfx::PNGCodec::FORMAT_BGRA,
                        snapshot_bounds.size(),
                        snapshot_bounds.width() * 4, true,
                        std::vector<gfx::PNGCodec::Comment>(),
                        png_representation);

  ReleaseDC(window_handle, window_hdc);

  return true;
}

}  // namespace browser
