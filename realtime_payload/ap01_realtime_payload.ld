OUTPUT_ARCH(riscv)
ENTRY(ap01_quota_ui_timer_wrapper)

/* file 0x230000 maps to VA 0xa022f000 (VA = file + 0x9ffff000).
 * This starts after the largest 221,445-byte dashboard accepted by all five
 * pet slots, rather than depending on one particular generated GIF length.
 */
PAYLOAD_VA = 0xa022f000;

SECTIONS
{
  . = PAYLOAD_VA;

  .payload : ALIGN(4)
  {
    KEEP(*(.text.entry))
    *(.text .text.*)
    *(.rodata .rodata.*)
  }

  .data : ALIGN(4)
  {
    *(.data .data.*)
    *(.sdata .sdata.*)
  }

  .bss (NOLOAD) : ALIGN(4)
  {
    *(.bss .bss.*)
    *(.sbss .sbss.*)
    *(COMMON)
  }

  /DISCARD/ :
  {
    *(.comment)
    *(.eh_frame*)
    *(.note*)
  }
}

ASSERT(SIZEOF(.data) == 0, "payload must not contain writable .data")
ASSERT(SIZEOF(.bss) == 0, "payload must not contain writable .bss")
