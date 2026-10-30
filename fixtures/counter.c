/* Minimal real SBF counter. Single program-owned writable 8-byte account.
 * ABI: instruction 0 initializes zero; instruction 1 increments uint64.
 * No syscalls, authorities or external dependencies. Not production code.
 */
typedef unsigned char u8;
typedef unsigned long long u64;
__attribute__((visibility("default")))
u64 entrypoint(const u8 *input) {
    if (*(const u64 *)input != 1) return 1;
    if (input[8] != 255 || !input[10]) return 2;
    u64 len = *(const u64 *)(input + 88);
    if (len != 8) return 3;
    const u8 *tail = input + 96 + len + 10240;
    tail = (const u8 *)(((u64)tail + 7) & ~7ULL);
    tail += 8; /* rent epoch */
    if (*(const u64 *)tail != 1) return 4;
    u8 op = tail[8];
    const u8 *program_id = tail + 9;
    for (int i=0; i<32; i++) if (input[48+i] != program_id[i]) return 5;
    u64 *counter = (u64 *)(input + 96);
    if (op == 0) { *counter = 0; return 0; }
    if (op == 1 && *counter != ~0ULL) { *counter += 1; return 0; }
    return 6;
}
