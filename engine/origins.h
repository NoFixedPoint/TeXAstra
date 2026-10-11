/* Included by the pinned LuaHBTeX scanner. Metadata never changes token values. */
extern int bako_origin;
extern int bako_attribute;
extern int bako_after_origin;
extern int *bako_token_origins;
extern void bako_token_store(unsigned p);
extern int bako_token_origin(unsigned p);
extern void bako_origin_copy(unsigned to, unsigned from);
extern void bako_source_open(const char *name);
extern void bako_scan_begin(void);
extern void bako_scan_end(void);
