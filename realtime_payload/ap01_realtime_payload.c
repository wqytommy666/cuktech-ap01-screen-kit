/*
 * AP01 local quota GIF loader.
 *
 * This payload is linked directly into an unused, zero-filled tail of the
 * shortened first pet GIF resource.  It deliberately has no writable global
 * state and no C library dependency.  The synchronous stock weather request
 * owns a stack download_state while webclient_perform invokes quota_sink.
 * Completion is published through a small tmpfs metadata file.  The LVGL
 * one-second timer consumes that metadata on the UI thread.
 *
 * There is no verified rename() entry point in firmware 1.0.2_0031.  Three
 * tmpfs GIF slots plus an applied ACK provide the same atomicity without
 * guessing an ABI.  The worker never truncates either the last published slot
 * or the slot currently acknowledged by LVGL, closes the third slot, and only
 * then publishes a checksummed metadata record.
 */

typedef unsigned char u8;
typedef unsigned int u32;

#define ATTR_ENTRY __attribute__((section(".text.entry"), noinline, used))
#define ATTR_NOINLINE __attribute__((noinline))

/* Verified firmware 1.0.2_0031 entry points. */
#define VA_STOCK_UI_TIMER                 0xa00bb5dau
#define VA_WINDOW_BY_INDEX                0xa00c5d84u
#define VA_LV_GIF_SET_SRC                 0xa00cf8d8u
#define VA_WEBCLIENT_PERFORM              0xa00d86bau
#define VA_OPEN                           0xa003f448u
#define VA_CLOSE                          0xa0026788u
#define VA_READ                           0xa003f5f4u
#define VA_WRITE                          0xa0027d94u

/* AP01/NuttX open flags recovered from stock call sites. */
#define AP01_O_RDONLY                     1
#define AP01_O_RDWR_CREAT_TRUNC           39
#define AP01_MODE_0666                    438

#define ERR_IO                            (-5)
#define ERR_INVAL                         (-22)
#define ERR_FBIG                          (-27)

#define GIF_MAX_BYTES                     (256u * 1024u)
#define GIF_MIN_BYTES                     13u

#define META_MAGIC                        0x46494751u /* "QGIF" little endian */
#define META_SALT                         0xa501a501u
#define META_GENERATION_MASK              0x7fffffffu

/* Exact webclient_context offsets for this 32-bit build. */
#define WEBCLIENT_SINK_ARG_OFFSET         64u
#define WEBCLIENT_HTTP_STATUS_OFFSET      96u

typedef void (*void_one_arg_fn)(void *);
typedef void *(*window_by_index_fn)(void *, int);
typedef void (*gif_set_src_fn)(void *, const void *);
typedef int (*webclient_perform_fn)(void *);
typedef int (*open_fn)(const char *, int, int);
typedef int (*close_fn)(int);
typedef int (*io_fn)(int, void *, u32);
typedef int (*write_fn)(int, const void *, u32);

struct quota_meta
{
  u32 magic;
  u32 generation;
  u32 slot;
  u32 check;
};

struct download_state
{
  int fd;
  u32 total;
  u32 header_len;
  u32 slot;
  u32 generation;
  u8 header[10];
  u8 last_byte;
};

static const char quota_slot0_path[] = "/tmp/.ap01q0.gif";
static const char quota_slot1_path[] = "/tmp/.ap01q1.gif";
static const char quota_slot2_path[] = "/tmp/.ap01q2.gif";
static const char quota_meta_path[] = "/tmp/.ap01q.meta";
static const char quota_ack_path[] = "/tmp/.ap01q.ack";

static ATTR_NOINLINE int fw_open(const char *path, int flags, int mode)
{
  return ((open_fn)VA_OPEN)(path, flags, mode);
}

static ATTR_NOINLINE int fw_close(int fd)
{
  return ((close_fn)VA_CLOSE)(fd);
}

static ATTR_NOINLINE int fw_read(int fd, void *buffer, u32 length)
{
  return ((io_fn)VA_READ)(fd, buffer, length);
}

static ATTR_NOINLINE int fw_write(int fd, const void *buffer, u32 length)
{
  return ((write_fn)VA_WRITE)(fd, buffer, length);
}

static const char *slot_path(u32 slot)
{
  if (slot == 0u)
    {
      return quota_slot0_path;
    }

  return slot == 1u ? quota_slot1_path : quota_slot2_path;
}

static u32 meta_check(const struct quota_meta *meta)
{
  return meta->magic ^ meta->generation ^ meta->slot ^ META_SALT;
}

static int meta_valid(const struct quota_meta *meta)
{
  return meta->magic == META_MAGIC &&
         meta->generation != 0u &&
         meta->generation <= META_GENERATION_MASK &&
         meta->slot <= 2u &&
         meta->check == meta_check(meta);
}

static ATTR_NOINLINE int read_exact(int fd, void *buffer, u32 length)
{
  u8 *cursor = (u8 *)buffer;
  u32 done = 0u;

  while (done < length)
    {
      int amount = fw_read(fd, cursor + done, length - done);
      if (amount <= 0 || (u32)amount > length - done)
        {
          return ERR_IO;
        }

      done += (u32)amount;
    }

  return 0;
}

static ATTR_NOINLINE int write_all(int fd, const void *buffer, u32 length)
{
  const u8 *cursor = (const u8 *)buffer;
  u32 done = 0u;

  while (done < length)
    {
      int amount = fw_write(fd, cursor + done, length - done);
      if (amount <= 0 || (u32)amount > length - done)
        {
          return ERR_IO;
        }

      done += (u32)amount;
    }

  return 0;
}

static ATTR_NOINLINE int read_record(const char *path, struct quota_meta *meta)
{
  int fd = fw_open(path, AP01_O_RDONLY, 0);
  int result;

  if (fd < 0)
    {
      return ERR_IO;
    }

  result = read_exact(fd, meta, (u32)sizeof(*meta));
  if (fw_close(fd) < 0)
    {
      result = ERR_IO;
    }

  if (result < 0 || !meta_valid(meta))
    {
      return ERR_INVAL;
    }

  return 0;
}

static ATTR_NOINLINE int write_record(const char *path, u32 generation,
                                      u32 slot)
{
  struct quota_meta meta;
  int fd;
  int result;

  meta.magic = META_MAGIC;
  meta.generation = generation;
  meta.slot = slot;
  meta.check = meta_check(&meta);

  fd = fw_open(path, AP01_O_RDWR_CREAT_TRUNC, AP01_MODE_0666);
  if (fd < 0)
    {
      return ERR_IO;
    }

  result = write_all(fd, &meta, (u32)sizeof(meta));
  if (fw_close(fd) < 0)
    {
      result = ERR_IO;
    }

  return result;
}

static int read_meta(struct quota_meta *meta)
{
  return read_record(quota_meta_path, meta);
}

static int read_ack(struct quota_meta *meta)
{
  return read_record(quota_ack_path, meta);
}

static int publish_meta(u32 generation, u32 slot)
{
  return write_record(quota_meta_path, generation, slot);
}

static int publish_ack(u32 generation, u32 slot)
{
  return write_record(quota_ack_path, generation, slot);
}

static int gif_header_valid(const u8 *header)
{
  int version_ok;

  version_ok = header[0] == (u8)'G' &&
               header[1] == (u8)'I' &&
               header[2] == (u8)'F' &&
               header[3] == (u8)'8' &&
               header[4] == (u8)'9' &&
               header[5] == (u8)'a';

  return version_ok &&
         header[6] == 0x40u && header[7] == 0x01u && /* 320 */
         header[8] == 0xf0u && header[9] == 0x00u;   /* 240 */
}

/* NuttX webclient_sink_callback_t ABI. */
ATTR_ENTRY int ap01_quota_sink(char **buffer, int offset, int datend,
                               int *buflen, void *argument)
{
  struct download_state *state = (struct download_state *)argument;
  const u8 *chunk;
  u32 length;
  u32 index;

  if (state == (void *)0 || buffer == (void *)0 || *buffer == (void *)0 ||
      buflen == (void *)0 || state->fd < 0 || offset < 0 || datend < offset ||
      *buflen < 0 || datend > *buflen)
    {
      return ERR_INVAL;
    }

  length = (u32)(datend - offset);
  if (length == 0u)
    {
      return 0;
    }

  if (length > GIF_MAX_BYTES || state->total > GIF_MAX_BYTES - length)
    {
      return ERR_FBIG;
    }

  chunk = (const u8 *)(*buffer) + (u32)offset;
  index = 0u;
  while (state->header_len < (u32)sizeof(state->header) && index < length)
    {
      state->header[state->header_len++] = chunk[index++];
    }

  if (state->header_len == (u32)sizeof(state->header) &&
      !gif_header_valid(state->header))
    {
      return ERR_INVAL;
    }

  if (write_all(state->fd, chunk, length) < 0)
    {
      return ERR_IO;
    }

  state->total += length;
  state->last_byte = chunk[length - 1u];
  return 0;
}

/* Replacement for the HTTP-path call to webclient_perform(ctx). */
ATTR_ENTRY int ap01_quota_webclient_wrapper(void *context)
{
  struct download_state state;
  struct quota_meta old_meta;
  struct quota_meta old_ack;
  u32 next_generation;
  u32 next_slot;
  u32 have_meta;
  u32 have_ack;
  int perform_result;
  int close_result;

  if (context == (void *)0)
    {
      return ERR_INVAL;
    }

  have_meta = read_meta(&old_meta) == 0 ? 1u : 0u;
  have_ack = read_ack(&old_ack) == 0 ? 1u : 0u;

  if (have_meta != 0u)
    {
      next_generation = (old_meta.generation + 1u) & META_GENERATION_MASK;
      if (next_generation == 0u)
        {
          next_generation = 1u;
        }
    }
  else
    {
      next_generation = 1u;
    }

  /* Exclude both the decoder's acknowledged slot and the last published slot
   * that the UI may adopt concurrently.  Three slots guarantee a free one.
   */
  for (next_slot = 0u; next_slot < 3u; ++next_slot)
    {
      if ((have_meta == 0u || next_slot != old_meta.slot) &&
          (have_ack == 0u || next_slot != old_ack.slot))
        {
          break;
        }
    }

  if (next_slot >= 3u)
    {
      return ERR_IO;
    }

  state.fd = fw_open(slot_path(next_slot), AP01_O_RDWR_CREAT_TRUNC,
                     AP01_MODE_0666);
  if (state.fd < 0)
    {
      return ERR_IO;
    }

  state.total = 0u;
  state.header_len = 0u;
  state.slot = next_slot;
  state.generation = next_generation;
  state.last_byte = 0u;

  /* Stock code already installs ap01_quota_sink at +60.  Supplying the
   * per-request stack state at +64 makes the callback re-entrant and avoids
   * an unverified writable global address.
   */
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = &state;
  perform_result = ((webclient_perform_fn)VA_WEBCLIENT_PERFORM)(context);
  *(void **)((u8 *)context + WEBCLIENT_SINK_ARG_OFFSET) = (void *)0;

  close_result = fw_close(state.fd);
  state.fd = -1;

  if (perform_result < 0)
    {
      return perform_result;
    }

  if (*(u32 *)((u8 *)context + WEBCLIENT_HTTP_STATUS_OFFSET) != 200u ||
      close_result < 0)
    {
      return ERR_IO;
    }

  if (state.total < GIF_MIN_BYTES || state.total > GIF_MAX_BYTES ||
      state.header_len != (u32)sizeof(state.header) ||
      !gif_header_valid(state.header) || state.last_byte != 0x3bu)
    {
      return ERR_INVAL;
    }

  if (publish_meta(state.generation, state.slot) < 0)
    {
      return ERR_IO;
    }

  return 0;
}

/* Replacement callback pointer for the stock one-second LVGL timer. */
ATTR_ENTRY void ap01_quota_ui_timer_wrapper(void *timer)
{
  struct quota_meta meta;
  struct quota_meta ack;
  void *theme;
  void *window;
  void *wrapper;
  void *state;
  void *gif;

  ((void_one_arg_fn)VA_STOCK_UI_TIMER)(timer);

  if (timer == (void *)0 || read_meta(&meta) < 0)
    {
      return;
    }

  theme = *(void **)((u8 *)timer + 12u);
  if (theme == (void *)0)
    {
      return;
    }

  window = ((window_by_index_fn)VA_WINDOW_BY_INDEX)(theme, 7);
  if (window == (void *)0)
    {
      return;
    }

  wrapper = *(void **)((u8 *)window + 16u);
  if (wrapper == (void *)0)
    {
      return;
    }

  state = *(void **)((u8 *)wrapper + 4u);
  if (state == (void *)0)
    {
      return;
    }

  gif = *(void **)state;
  if (gif == (void *)0)
    {
      return;
    }

  if (read_ack(&ack) == 0 && ack.generation == meta.generation &&
      ack.slot == meta.slot)
    {
      return;
    }

  ((gif_set_src_fn)VA_LV_GIF_SET_SRC)(gif, slot_path(meta.slot));
  /* In this LVGL build gif+0x5c is the decoder descriptor.  Acknowledge only
   * after lv_gif_set_src created it; otherwise retry on the next UI tick.
   */
  if (*(void **)((u8 *)gif + 0x5cu) != (void *)0)
    {
      (void)publish_ack(meta.generation, meta.slot);
    }
}
