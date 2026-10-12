/* Included by the pinned LuaHBTeX scanner. Metadata never changes token values. */
extern int bako_origin;
extern int bako_attribute;
extern int bako_after_origin;
/* Token cells use negative origins for literal macro replacement text, which
 * maps to the invocation when expanded. Positive captured origins survive
 * package-created definitions. bako_origin and node attributes stay positive. */
extern int *bako_token_origins;
extern void bako_token_store(unsigned p);
extern int bako_token_origin(unsigned p);
extern void bako_origin_copy(unsigned to, unsigned from);
extern void bako_source_open(const char *name);
extern void bako_scan_begin(void);
extern void bako_scan_end(void);
extern void (*bako_boundary_hook)(void);
