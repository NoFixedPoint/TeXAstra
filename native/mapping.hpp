#pragma once

namespace bako {
// PDF marked-content scopes are independent alignment anchors. An unexpected
// draw invalidates only its scope; later source IDs never shift along the page.
struct SourceDraw {
    fz_rect rect;
    fz_quad quad;
    int source;
    bool rule;
    const char *issue;
    int length = 0;
};
struct MappingTrace {
    struct Scope { int source, expected; bool rule, own; size_t start; int length = 0; };
    std::vector<SourceDraw> draws;
    std::vector<Scope> scopes;
    int external = 0;
    decltype(pdf_processor::op_BDC) bdc = nullptr;
    decltype(pdf_processor::op_BMC) bmc = nullptr;
    decltype(pdf_processor::op_EMC) emc = nullptr;
    decltype(pdf_processor::op_Do_form) form = nullptr;

    void draw(fz_rect box, bool rule = false, fz_quad quad = {}) {
        const auto *scope = scopes.empty() ? nullptr : &scopes.back();
        // Untagged paths (e.g. TikZ outlines) are not selectable TeX rules.
        if (rule && (external || !scope || !scope->rule)) return;
        int source = !external && scope ? scope->source : 0;
        draws.push_back({box, quad, source, rule, external ? "external-content" :
                         source > 0 ? nullptr : scope ? "missing-origin" : "untagged-content", scope ? scope->length : 0});
    }
    void close_scope() {
        if (scopes.empty()) return;
        auto scope = scopes.back(); scopes.pop_back();
        if (!scope.own || scope.rule) return;
        size_t glyphs = 0;
        for (size_t i=scope.start; i<draws.size(); ++i) if (!draws[i].rule) ++glyphs;
        if (glyphs != size_t(scope.expected)) {
            for (size_t i=scope.start; i<draws.size(); ++i) {
                draws[i].source=0; draws[i].issue="glyph-count-mismatch";
            }
        }
    }
};
// MuPDF's run processor has no user-data slot. A render owns this binding on
// its thread, clearing it in fz_always on both success and interpreter errors.
inline thread_local MappingTrace *active_mapping = nullptr;
inline void mapping_bdc(fz_context *ctx, pdf_processor *proc, const char *tag, pdf_obj *raw, pdf_obj *cooked) {
    auto &m=*active_mapping;
    // In the pinned MuPDF run processor ET only flushes accumulated glyphs.
    // Flush BEFORE changing ownership, including for nested marked content.
    proc->op_ET(ctx,proc);
    auto scope=m.scopes.empty() ? MappingTrace::Scope{0,0,false,false,m.draws.size()} : m.scopes.back();
    scope.own=false; scope.start=m.draws.size();
    if (!m.external && !strcmp(tag,"BakoSource")) {
        auto props=cooked ? cooked : raw;
        auto kind=pdf_dict_gets(ctx,props,"Kind");
        bool rule=!strcmp(pdf_to_name(ctx,kind),"Rule");
        bool glyph=!strcmp(pdf_to_name(ctx,kind),"Glyph");
        int source=pdf_to_int(ctx,pdf_dict_gets(ctx,props,"ID"));
        int count=pdf_to_int(ctx,pdf_dict_gets(ctx,props,"N"));
        bool valid=pdf_to_int(ctx,pdf_dict_gets(ctx,props,"V"))==1 && (rule||glyph) && source>=0 && count>=0;
        scope={valid ? source : 0,valid ? count : 0,valid && rule,true,m.draws.size()};
        scope.length=valid ? pdf_to_int(ctx,pdf_dict_gets(ctx,props,"Length")) : 0;
    }
    m.scopes.push_back(scope);
    m.bdc(ctx,proc,tag,raw,cooked);
}
inline void mapping_bmc(fz_context *ctx, pdf_processor *proc, const char *tag) {
    auto &m=*active_mapping; proc->op_ET(ctx,proc);
    auto scope=m.scopes.empty() ? MappingTrace::Scope{0,0,false,false,m.draws.size()} : m.scopes.back();
    scope.own=false; scope.start=m.draws.size(); m.scopes.push_back(scope);
    m.bmc(ctx,proc,tag);
}
inline void mapping_emc(fz_context *ctx, pdf_processor *proc) {
    auto &m=*active_mapping; proc->op_ET(ctx,proc);
    m.close_scope(); m.emc(ctx,proc);
}
inline void mapping_form(fz_context *ctx, pdf_processor *proc, const char *name, pdf_obj *object) {
    auto &m=*active_mapping; proc->op_ET(ctx,proc);
    ++m.external;
    fz_try(ctx) { m.form(ctx,proc,name,object); proc->op_ET(ctx,proc); }
    fz_always(ctx) { --m.external; }
    fz_catch(ctx) { fz_rethrow(ctx); }
}
inline void bind_mapping(pdf_processor *proc, MappingTrace &m) {
    active_mapping=&m;
    m.bdc=proc->op_BDC; m.bmc=proc->op_BMC; m.emc=proc->op_EMC; m.form=proc->op_Do_form;
    proc->op_BDC=mapping_bdc; proc->op_BMC=mapping_bmc; proc->op_EMC=mapping_emc; proc->op_Do_form=mapping_form;
}
} // namespace bako
