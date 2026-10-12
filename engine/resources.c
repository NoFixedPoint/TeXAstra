/* Identify ordinary file-backed raster images used by the current page.
 * Names alone are unsafe after rollback: /Im1 can denote a different file.
 * Custom dictionaries, forms and non-raster resources retain the fallback.
 */
int bako_page_image_resources(lua_State *L)
{
    PDF pdf = static_pdf;
    pdf_object_list *ol;
    lua_newtable(L);
    if (pdf_page_resources != null) return 1;
    for (ol = get_page_resources_list(pdf, obj_type_ximage); ol; ol = ol->link) {
        image_dict *image = idict_array[obj_data_ptr(pdf, ol->info)];
        if ((img_type(image) != IMG_TYPE_PNG && img_type(image) != IMG_TYPE_JPG) ||
            !img_filepath(image) || img_colorspace(image) != 0 ||
            (img_attr(image) && *img_attr(image))) continue;
        lua_pushfstring(L, "Im%d%s", obj_info(pdf, ol->info), pdf->resname_prefix ? pdf->resname_prefix : "");
        lua_newtable(L);
        lua_pushstring(L, img_filepath(image)); lua_setfield(L, -2, "path");
        lua_pushfstring(L, "%d|%d|%d|%d|%d|%d|%d|%d", (int)img_type(image),
            img_xsize(image), img_ysize(image), img_colordepth(image),
            img_xres(image), img_yres(image), img_orientation(image), img_transform(image));
        lua_setfield(L, -2, "properties");
        lua_pushfstring(L, "%d|%d|%d|%d|%d|%d", pdf->gamma, pdf->image_gamma,
            pdf->image_apply_gamma, pdf->image_hicolor, pdf->major_version, pdf->minor_version);
        lua_setfield(L, -2, "settings");
        lua_settable(L, -3);
    }
    return 1;
}

/* Font-only resource export, included by pdfgen.c (LuaHBTeX 1.14).
 * Called ONLY in a disposable fork. No page finishing or further typesetting.
 * The caller owns the fresh output FILE and discards the child afterwards.
 */
int bako_write_font_bundle(FILE *out, const int *fonts, int count)
{
    PDF pdf = static_pdf;
    int i, j, f, pages, root;
    if (count < 1 || count > 256 || pdf->os_enable || pdf->stream_writing)
        return 0;
    for (i = 0; i < count; ++i) {
        f = fonts[i];
        if (f <= 0 || f > max_font_id() || !font_used(f) || pdf_font_num(f) <= 0 ||
            (pdf_font_attr(f) && pdf_font_attr(f) != get_nullstr()))
            return 0;
        /* Type 3 fonts can invoke user code or reference existing XObjects.
         * Leave them on the normal document-finalization fallback. */
        if (font_encodingbytes(f) != 2 &&
            ((font_psname(f) && strstr(font_psname(f), "none")) || !font_map(f) ||
             (!font_map(f)->ps_name && !font_map(f)->ff_name)))
            return 0;
    }
    /* Discard the document prefix, but preserve object numbers used by the
     * engine font writer. Unexported objects become free xref entries. */
    pdf->file = out;
    pdf->gone = 0;
    pdf->buf->p = pdf->buf->data;
    pdf->cave = 0;
    for (i = 0; i <= pdf->obj_ptr; ++i) set_obj_fresh(pdf, i);
    pdf_puts(pdf, "%PDF-1.7\n");
    pdf->gen_tounicode = pdf_gen_tounicode;
    pdf->omit_cidset = pdf_omit_cidset;
    pdf->omit_charset = pdf_omit_charset;
    /* Merge used glyphs from font aliases (different sizes, etc.), exactly as
     * the ordinary finalizer does before writing font subsets. */
    for (i = 0; i < count; ++i) {
        f = fonts[i];
        for (j = 1; j <= max_font_id(); ++j) {
            if (font_used(j) && pdf_font_num(j) == -f) {
                int c;
                if (pdf_font_attr(j) && pdf_font_attr(j) != get_nullstr()) return 0;
                for (c = font_bc(j); c <= font_ec(j); ++c)
                    if (quick_char_exists(j, c) && pdf_char_marked(j, c)) pdf_mark_char(f, c);
            }
        }
        do_pdf_font(pdf, f);
    }
    write_fontstuff(pdf);
    for (i = 0; i < count; ++i)
        if (!is_obj_written(pdf, pdf_font_num(fonts[i]))) return 0;
    pages = pdf_create_obj(pdf, obj_type_others, 0);
    pdf_begin_obj(pdf, pages, OBJSTM_NEVER);
    pdf_puts(pdf, "<< /Type /Pages /Count 0 /Kids [] >>\n");
    pdf_end_obj(pdf);
    root = pdf_create_obj(pdf, obj_type_others, 0);
    pdf_begin_obj(pdf, root, OBJSTM_NEVER);
    pdf_begin_dict(pdf);
    pdf_dict_add_name(pdf, "Type", "Catalog");
    pdf_dict_add_ref(pdf, "Pages", pages);
    pdf_add_name(pdf, "BakoFonts");
    pdf_begin_dict(pdf);
    for (i = 0; i < count; ++i) {
        pdf_printf(pdf, "/F%d", fonts[i]);
        pdf_print_resname_prefix(pdf);
        pdf_out(pdf, ' ');
        pdf_add_ref(pdf, pdf_font_num(fonts[i]));
    }
    pdf_end_dict(pdf);
    pdf_end_dict(pdf);
    pdf_end_obj(pdf);
    build_free_object_list(pdf);
    pdf_save_offset(pdf);
    pdf_printf(pdf, "xref\n0 %d\n", pdf->obj_ptr + 1);
    pdf_print_fw_int(pdf, obj_link(pdf, 0));
    pdf_puts(pdf, " 65535 f \n");
    for (i = 1; i <= pdf->obj_ptr; ++i) {
        pdf_print_fw_int(pdf, is_obj_written(pdf, i) ? obj_offset(pdf, i) : obj_link(pdf, i));
        pdf_puts(pdf, is_obj_written(pdf, i) ? " 00000 n \n" : " 00000 f \n");
    }
    pdf_puts(pdf, "trailer\n");
    pdf_begin_dict(pdf);
    pdf_dict_add_int(pdf, "Size", pdf->obj_ptr + 1);
    pdf_dict_add_ref(pdf, "Root", root);
    pdf_end_dict(pdf);
    pdf_puts(pdf, "\nstartxref\n");
    pdf_add_longint(pdf, (longinteger) pdf->save_offset);
    pdf_puts(pdf, "\n%%EOF\n");
    pdf_flush(pdf);
    return fflush(out) == 0;
}
