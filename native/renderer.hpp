#pragma once
#include "source.hpp"
#include <mupdf/fitz.h>
#include <mupdf/pdf.h>
#include <libdeflate.h>
#ifndef _WIN32
#include <zlib.h>
#endif
#include <cmath>
#include <cfloat>
#include "mapping.hpp"

namespace bako {
inline Json rectangle(fz_rect r) {
    return Json::array({r.x0, r.y0, r.x1, r.y1});
}
struct PageBuffer {
    Json metadata;
    std::string commands;
    std::vector<int> ids;
};
struct ResourceMiss : std::runtime_error {
    using std::runtime_error::runtime_error;
};
struct FontResourceMiss : ResourceMiss { using ResourceMiss::ResourceMiss; };

// Preserve the established PyMuPDF 1.26.7 texttrace geometry convention.
// The font-normalized geometry and quad correction follow that project's
// src/extra.i (AGPL-3.0); see THIRD_PARTY.md. No Python objects are constructed.
struct TraceDevice {
    fz_device super;
    MappingTrace *mapping;
};
inline void trace_text(fz_context *ctx, fz_device *dev, const fz_text *text, fz_matrix ctm) {
    auto &mapping = *reinterpret_cast<TraceDevice *>(dev)->mapping;
    for (auto span = text->head; span; span = span->next) {
        auto mat = fz_concat(span->trm, ctm);
        auto direction = fz_transform_vector(fz_make_point(1, 0), mat);
        double size = std::sqrt(direction.x * direction.x + direction.y * direction.y);
        direction = fz_normalize_vector(direction);
        double asc = fz_font_ascender(ctx, span->font), dsc = fz_font_descender(ctx, span->font);
        if (asc < 1e-3) {
            asc = .9;
            dsc = -.1;
        }
        double top = asc * size / (asc - dsc), bottom = dsc * size / (asc - dsc);
        auto rotation = fz_make_matrix(direction.x, direction.y, -direction.y, direction.x, 0, 0);
        if (direction.x == -1) {
            rotation.d = 1;
        }
        for (int i = 0; i < span->len; ++i) {
            auto item = span->items[i];
            // MuPDF adds gid=-1 entries for extra Unicode characters in one
            // ligature. Provenance records physical glyphs, not those entries.
            if (item.gid < 0) continue;
            double advance =
                item.gid >= 0 ? fz_advance_glyph(ctx, span->font, item.gid, span->wmode) * size : 0;
            auto origin = fz_transform_point(fz_make_point(item.x, item.y), ctm);
            auto around = fz_concat(fz_concat(fz_translate(-origin.x, -origin.y), rotation),
                                    fz_translate(origin.x, origin.y));
            bool flip = (mat.d > 0 && (direction.x == 1 || direction.x == -1)) ||
                        (mat.b != 0 && mat.b == -mat.c);
            auto box = fz_make_rect(origin.x, flip ? origin.y + bottom : origin.y - top,
                                    origin.x + advance, flip ? origin.y + top : origin.y - bottom);
            mapping.draw(fz_transform_rect(box, around));
        }
    }
}
inline void trace_fill(fz_context *c, fz_device *d, const fz_text *t, fz_matrix m, fz_colorspace *,
                       const float *, float, fz_color_params) {
    trace_text(c, d, t, m);
}
inline void trace_stroke(fz_context *c, fz_device *d, const fz_text *t, const fz_stroke_state *,
                         fz_matrix m, fz_colorspace *, const float *, float, fz_color_params) {
    trace_text(c, d, t, m);
}
inline void trace_rule_fill(fz_context *c, fz_device *d, const fz_path *path, int,
                            fz_matrix m, fz_colorspace *, const float *, float, fz_color_params) {
    auto quad=fz_transform_quad(fz_quad_from_rect(fz_bound_path(c,path,nullptr,fz_identity)),m);
    reinterpret_cast<TraceDevice *>(d)->mapping->draw(fz_rect_from_quad(quad),true,quad);
}
inline void trace_rule_stroke(fz_context *c, fz_device *d, const fz_path *path, const fz_stroke_state *stroke,
                              fz_matrix m, fz_colorspace *, const float *, float, fz_color_params) {
    auto quad=fz_transform_quad(fz_quad_from_rect(fz_bound_path(c,path,stroke,fz_identity)),m);
    reinterpret_cast<TraceDevice *>(d)->mapping->draw(fz_rect_from_quad(quad),true,quad);
}
inline fz_rect selection_box(fz_context *ctx, fz_stext_line *line, fz_stext_char *ch) {
    auto quad = ch->quad;
    float asc = fz_font_ascender(ctx, ch->font), dsc = fz_font_descender(ctx, ch->font),
          difference = asc - dsc + FLT_EPSILON;
    if (!line->wmode && difference < 1) {
        if (asc < 1e-3) {
            asc = .9f;
            dsc = -.1f;
            difference = 1;
        }
        asc /= difference;
        dsc /= difference;
        difference = asc - dsc;
        asc = asc * ch->size / difference;
        dsc = dsc * ch->size / difference;
        auto unrotate = fz_make_matrix(line->dir.x, -line->dir.y, line->dir.y, line->dir.x, 0, 0);
        auto rotate = fz_make_matrix(line->dir.x, line->dir.y, -line->dir.y, line->dir.x, 0, 0);
        if (line->dir.x == -1) {
            unrotate.d = 1;
            rotate.d = 1;
        }
        quad = fz_transform_quad(
            fz_transform_quad(quad, fz_translate(-ch->origin.x, -ch->origin.y)), unrotate);
        bool flip = line->dir.x == 1 && quad.ul.y > 0;
        quad.ul.y = quad.ur.y = flip ? asc : -asc;
        quad.ll.y = quad.lr.y = flip ? dsc : -dsc;
        if (quad.ll.x < 0) {
            quad.ll.x = quad.ul.x = 0;
        }
        if (quad.lr.x - quad.ll.x < FLT_EPSILON) {
            auto glyph = fz_encode_character(ctx, ch->font, ch->c);
            if (glyph) {
                quad.lr.x =
                    quad.ll.x + fz_advance_glyph(ctx, ch->font, glyph, line->wmode) * ch->size;
                quad.ur.x = quad.lr.x;
            }
        }
        quad = fz_transform_quad(fz_transform_quad(quad, rotate),
                                 fz_translate(ch->origin.x, ch->origin.y));
    }
    auto box = fz_rect_from_quad(quad);
    if (line->wmode && box.y1 < box.y0 + ch->size) {
        box.y0 = box.y1 - ch->size;
    }
    return box;
}

class Renderer {
    fz_context *ctx = nullptr;
    pdf_document *doc = nullptr;
    libdeflate_compressor *compressor = nullptr;
    std::set<std::string> coverage;
    std::map<int, std::set<std::string>> page_coverage;
    static void integer(std::string &s, uint32_t n) {
        for (int shift : {24, 16, 8, 0}) {
            s += char(n >> shift);
        }
    }
    static void chunk(std::string &s, const char *type, const std::string &data) {
        integer(s, data.size());
        size_t start = s.size();
        s.append(type, 4);
        s += data;
#ifdef _WIN32
        integer(s, libdeflate_crc32(0, s.data() + start, 4 + data.size()));
#else
        integer(s, crc32(0, reinterpret_cast<const Bytef *>(s.data() + start), 4 + data.size()));
#endif
    }
    std::string png(fz_pixmap *pix) {
        int width = fz_pixmap_width(ctx, pix), height = fz_pixmap_height(ctx, pix),
            stride = fz_pixmap_stride(ctx, pix);
        auto pixels = fz_pixmap_samples(ctx, pix);
        size_t row = size_t(width) * 3;
        std::string rows((row + 1) * height, '\0');
        for (int y = 0; y < height; ++y) {
            std::memcpy(rows.data() + y * (row + 1) + 1, pixels + y * stride, row);
        }
        std::string compressed(libdeflate_zlib_compress_bound(compressor, rows.size()), '\0');
        auto size = libdeflate_zlib_compress(compressor, rows.data(), rows.size(),
                                             compressed.data(), compressed.size());
        if (!size) {
            throw std::runtime_error("PNG compression failed");
        }
        compressed.resize(size);
        std::string out = "\x89PNG\r\n\x1a\n", header;
        integer(header, width);
        integer(header, height);
        header.append("\x08\x02\0\0\0", 5);
        chunk(out, "IHDR", header);
        chunk(out, "IDAT", compressed);
        chunk(out, "IEND", "");
        return out;
    }

  public:
    Renderer() {
        ctx = fz_new_context(nullptr, nullptr, FZ_STORE_DEFAULT);
        if (!ctx) {
            throw std::runtime_error("Cannot create MuPDF context");
        }
        compressor = libdeflate_alloc_compressor(1);
        if (!compressor) {
            throw std::runtime_error("Cannot create PNG compressor");
        }
    }
    Renderer(const Renderer &) = delete;
    Renderer &operator=(const Renderer &) = delete;
    ~Renderer() {
        if (doc) {
            pdf_drop_document(ctx, doc);
        }
        if (compressor) {
            libdeflate_free_compressor(compressor);
        }
        if (ctx) {
            fz_drop_context(ctx);
        }
    }
    int pages() const {
        return doc ? pdf_count_pages(ctx, doc) : 0;
    }
    Json layout() {
        Json result=Json::array();
        fz_page *page=nullptr;
        fz_var(page);
        fz_try(ctx) {
            for (int n=0;n<pages();++n) {
                page=reinterpret_cast<fz_page *>(pdf_load_page(ctx,doc,n));
                auto bounds=fz_bound_page(ctx,page);
                result.push_back(Json::array({bounds.x1-bounds.x0,bounds.y1-bounds.y0}));
                fz_drop_page(ctx,page);page=nullptr;
            }
        }
        fz_always(ctx) { fz_drop_page(ctx,page); }
        fz_catch(ctx) { throw std::runtime_error(fz_caught_message(ctx)); }
        return result;
    }
    void seed(const fs::path &path, std::set<std::string> resources) {
        pdf_document *replacement = nullptr;
        fz_buffer *bytes = nullptr;
        fz_stream *stream = nullptr;
        fz_var(replacement); fz_var(bytes); fz_var(stream);
        fz_try(ctx) {
            // MuPDF reads objects lazily. An early compiler checkpoint may
            // rewrite the output file, so retain an immutable resource seed.
            bytes = fz_read_file(ctx, path.u8string().c_str());
            stream = fz_open_buffer(ctx, bytes);
            replacement = pdf_open_document_with_stream(ctx, stream);
        }
        fz_always(ctx) { fz_drop_stream(ctx, stream); fz_drop_buffer(ctx, bytes); }
        fz_catch(ctx) {
            throw std::runtime_error(fz_caught_message(ctx));
        }
        if (doc) {
            pdf_drop_document(ctx, doc);
        }
        doc = replacement;
        coverage = std::move(resources);
        page_coverage.clear();
    }
    static std::set<std::string> font_names(const PageBuffer &buffer) {
        static const std::regex names(R"(/([^\s/]+)\s+[-+.\d]+\s+Tf\b)");
        std::set<std::string> result;
        for (auto it = std::sregex_iterator(buffer.commands.begin(), buffer.commands.end(), names);
             it != std::sregex_iterator(); ++it) result.insert((*it)[1]);
        return result;
    }
    void import_fonts(const PageBuffer &buffer, const std::string &bytes) {
        const int number = buffer.metadata.at("page");
        const auto names = font_names(buffer);
        if (names.empty()) throw ResourceMiss("No supported font names in page commands");
        pdf_document *bundle = nullptr;
        fz_stream *stream = nullptr;
        pdf_graft_map *map = nullptr;
        pdf_obj *resources = nullptr, *fonts = nullptr, *imported = nullptr;
        fz_var(bundle); fz_var(stream); fz_var(map); fz_var(resources); fz_var(fonts); fz_var(imported);
        bool failed = false;
        fz_var(failed);
        fz_try(ctx) {
            stream = fz_open_memory(ctx, reinterpret_cast<const unsigned char *>(bytes.data()), bytes.size());
            bundle = pdf_open_document_with_stream(ctx, stream);
            auto incoming = pdf_dict_gets(ctx, pdf_dict_get(ctx, pdf_trailer(ctx, bundle), PDF_NAME(Root)), "BakoFonts");
            for (const auto &name : names) {
                auto font = pdf_dict_gets(ctx, incoming, name.c_str());
                if (!pdf_name_eq(ctx, pdf_dict_get(ctx, font, PDF_NAME(Type)), PDF_NAME(Font)))
                    fz_throw(ctx, FZ_ERROR_FORMAT, "Missing font in resource bundle");
            }
            auto object = pdf_lookup_page_obj(ctx, doc, number);
            // Page dictionaries may share inherited resources. Only this page
            // gets the new subset; other pages keep their known font versions.
            resources = pdf_copy_dict(ctx, pdf_dict_get_inheritable(ctx, object, PDF_NAME(Resources)));
            fonts = pdf_new_dict(ctx, doc, static_cast<int>(names.size()));
            map = pdf_new_graft_map(ctx, doc);
            for (const auto &name : names) {
                imported = pdf_graft_mapped_object(ctx, map, pdf_dict_gets(ctx, incoming, name.c_str()));
                pdf_dict_puts(ctx, fonts, name.c_str(), imported);
                pdf_drop_obj(ctx, imported); imported = nullptr;
            }
            pdf_dict_put(ctx, resources, PDF_NAME(Font), fonts);
            pdf_dict_put(ctx, object, PDF_NAME(Resources), resources);
        }
        fz_always(ctx) {
            pdf_drop_obj(ctx, imported); pdf_drop_obj(ctx, fonts); pdf_drop_obj(ctx, resources);
            pdf_drop_graft_map(ctx, map); pdf_drop_document(ctx, bundle); fz_drop_stream(ctx, stream);
        }
        fz_catch(ctx) { failed = true; }
        if (failed) throw ResourceMiss("Font resource bundle could not be imported");
        std::set<std::string> known;
        for (const auto &value : buffer.metadata.at("coverage")) known.insert(value.get<std::string>());
        page_coverage[number] = std::move(known);
    }
    void update(const PageBuffer &buffer) {
        int page = buffer.metadata.at("page");
        if (page >= pages()) {
            throw ResourceMiss("New physical page requires a resource refresh");
        }
        static const std::regex external(R"(/[^\s/]+\s+(Do|gs|sh|CS|cs)\b|\b(SCN|scn)\b)");
        if (std::regex_search(buffer.commands, external)) {
            throw ResourceMiss("External graphics resource requires a refresh");
        }
        const auto &known = page_coverage.count(page) ? page_coverage.at(page) : coverage;
        for (const auto &value : buffer.metadata.at("coverage")) {
            if (!known.count(value.get<std::string>()))
                throw FontResourceMiss("New font or glyph requires a resource refresh");
        }
        bool missing = false, bad_size = false, bad_stream = false;
        fz_try(ctx) {
            auto object = pdf_lookup_page_obj(ctx, doc, page);
            fz_rect bounds;
            fz_matrix transform;
            pdf_page_obj_transform(ctx, object, &bounds, &transform);
            bounds = fz_transform_rect(bounds, transform);
            bad_size =
                std::abs((bounds.x1 - bounds.x0) - buffer.metadata.at("width").get<double>()) >
                    .01 ||
                std::abs((bounds.y1 - bounds.y0) - buffer.metadata.at("height").get<double>()) >
                    .01;
            auto fonts = pdf_dict_get(
                ctx, pdf_dict_get_inheritable(ctx, object, PDF_NAME(Resources)), PDF_NAME(Font));
            static const std::regex font_names(R"(/([^\s/]+)\s+[-+.\d]+\s+Tf\b)");
            for (auto it = std::sregex_iterator(buffer.commands.begin(), buffer.commands.end(),
                                                font_names);
                 it != std::sregex_iterator(); ++it) {
                if (!pdf_dict_gets(ctx, fonts, (*it)[1].str().c_str())) {
                    missing = true;
                }
            }
            auto content = pdf_dict_get(ctx, object, PDF_NAME(Contents));
            if (pdf_is_array(ctx, content)) {
                bad_stream = pdf_array_len(ctx, content) != 1;
                content = pdf_array_get(ctx, content, 0);
            }
            bad_stream = bad_stream || !pdf_is_stream(ctx, content);
            if (!missing && !bad_size && !bad_stream) {
                auto bytes = fz_new_buffer_from_copied_data(
                    ctx, reinterpret_cast<const unsigned char *>(buffer.commands.data()),
                    buffer.commands.size());
                pdf_update_stream(ctx, doc, content, bytes, 0);
                fz_drop_buffer(ctx, bytes);
            }
        }
        fz_catch(ctx) {
            throw std::runtime_error(fz_caught_message(ctx));
        }
        if (missing) {
            throw FontResourceMiss("Page font dictionary changed");
        }
        if (bad_size) {
            throw ResourceMiss("Changed page dimensions");
        }
        if (bad_stream) {
            throw ResourceMiss("Expected one page stream");
        }
    }
    Json render(int number, const Sources &sources, const std::vector<int> &ids, bool source_sync = true) {
        (void)ids; // sidecar IDs are retained for forward-page lookup only
        auto started = Clock::now();
        number = std::clamp(number, 0, pages() - 1);
        fz_var(number);
        fz_page *page = nullptr;
        fz_display_list *display = nullptr;
        fz_pixmap *pix = nullptr;
        fz_stext_page *text = nullptr;
        fz_device *device = nullptr;
        pdf_processor *processor = nullptr;
        fz_var(page);
        fz_var(display);
        fz_var(pix);
        fz_var(text);
        fz_var(device);
        fz_var(processor);
        MappingTrace mapping;
        Json unmapped = Json::array();
        Json characters = Json::array(), regions = Json::array(), warnings = sources.warnings();
        fz_rect bounds = {};
        Json timings;
        std::string image;
        fz_try(ctx) {
            page = reinterpret_cast<fz_page *>(pdf_load_page(ctx, doc, number));
            bounds = fz_bound_page(ctx, page);
            display = fz_new_display_list_from_page_contents(ctx, page);
            auto listed = Clock::now();
            timings["displayList"] = elapsed(started);
            pix = fz_new_pixmap_from_display_list(ctx, display, fz_scale(1.4f, 1.4f),
                                                  fz_device_rgb(ctx), 0);
            auto raster = Clock::now();
            timings["raster"] = elapsed(listed);
            if (source_sync) {
                auto trace = fz_new_derived_device(ctx, TraceDevice);
                device = &trace->super; trace->mapping=&mapping;
                device->fill_text=trace_fill; device->stroke_text=trace_stroke; device->ignore_text=trace_text;
                device->fill_path=trace_rule_fill; device->stroke_path=trace_rule_stroke;
                fz_matrix transform; fz_rect media;
                auto pdfpage=reinterpret_cast<pdf_page *>(page);
                pdf_page_transform(ctx,pdfpage,&media,&transform);
                processor=pdf_new_run_processor(ctx,doc,device,transform,-1,"View",nullptr,nullptr,nullptr,nullptr,nullptr);
                bind_mapping(processor,mapping);
                pdf_process_contents(ctx,processor,doc,pdf_page_resources(ctx,pdfpage),pdf_page_contents(ctx,pdfpage),nullptr,nullptr);
                pdf_close_processor(ctx,processor);pdf_drop_processor(ctx,processor);processor=nullptr;
                fz_close_device(ctx,device);fz_drop_device(ctx,device);device=nullptr;
                active_mapping=nullptr;
                // Unclosed scopes are not trusted, even if their counts match.
                if (!mapping.scopes.empty()) {
                    for (size_t i=mapping.scopes.front().start;i<mapping.draws.size();++i) {
                        mapping.draws[i].source=0; mapping.draws[i].issue="unclosed-source-scope";
                    }
                }
                std::map<std::string,int> issues;
                for (const auto &draw : mapping.draws) {
                    if (fz_is_empty_rect(fz_intersect_rect(draw.rect,bounds))) continue;
                    const auto *span=draw.issue ? nullptr : sources.find(draw.source);
                    if (span) {
                        auto row=span->row(rectangle(draw.rect));
                        if (draw.rule) {
                            row[10]="rule-origin";
                            auto q=draw.quad;
                            row.push_back(Json::array({q.ul.x,q.ul.y,q.ur.x,q.ur.y,q.lr.x,q.lr.y,q.ll.x,q.ll.y}));
                        } else row.push_back(nullptr);
                        regions.push_back(std::move(row));
                    } else {
                        const char *issue=draw.issue ? draw.issue : "unknown-source";
                        unmapped.push_back({{"rect",rectangle(draw.rect)},{"reason",issue}});
                        ++issues[issue];
                    }
                }
                for (const auto &[issue,count] : issues) {
                    if (issue=="glyph-count-mismatch" || issue=="unclosed-source-scope" || issue=="unknown-source")
                        warnings.push_back({{"code",issue},{"regions",count},
                            {"reason","Some output has no verified source mapping; other regions remain navigable."}});
                }
            }
            auto origins = Clock::now();
            timings["origins"] = elapsed(raster);
            fz_stext_options options = {};
            options.flags = 199; // same RAWDICT extraction flags as the reference renderer
            text = fz_new_stext_page_from_display_list(ctx, display, &options);
            for (auto block = text->first_block; block; block = block->next) {
                if (block->type == FZ_STEXT_BLOCK_TEXT) {
                    for (auto line = block->u.t.first_line; line; line = line->next) {
                        for (auto ch = line->first_char; ch; ch = ch->next) {
                            auto box = selection_box(ctx, line, ch);
                            if (fz_is_empty_rect(fz_intersect_rect(box, bounds))) {
                                continue;
                            }
                            characters.push_back(Json::array({rune(ch->c), rectangle(box)}));
                        }
                    }
                }
            }
            auto extracted = Clock::now();
            timings["text"] = elapsed(origins);
            image = "data:image/png;base64," + base64(png(pix));
            timings["png"] = elapsed(extracted);
        }
        fz_always(ctx) {
            pdf_drop_processor(ctx, processor);
            fz_drop_device(ctx, device);
            fz_drop_stext_page(ctx, text);
            fz_drop_pixmap(ctx, pix);
            fz_drop_display_list(ctx, display);
            fz_drop_page(ctx, page);
            active_mapping=nullptr;
        }
        fz_catch(ctx) {
            throw std::runtime_error(fz_caught_message(ctx));
        }
        return {{"page", number},
                {"pageCount", pages()},
                {"width", bounds.x1 - bounds.x0},
                {"height", bounds.y1 - bounds.y0},
                {"image", std::move(image)},
                {"regionFields", Json::array({"id", "rect", "file", "start", "end", "line",
                                              "column", "endLine", "endColumn", "text", "kind", "quad"})},
                {"regionRows", std::move(regions)},
                {"characterRows", std::move(characters)},
                {"unmappedRegions", std::move(unmapped)},
                {"warnings", std::move(warnings)},
                {"renderStagesMs", timings},
                {"renderMs", elapsed(started)}};
    }
};
} // namespace bako
