#include <mbedtls/sha256.h>

#include <fmt/printf.h>

#include <string_view>

int main(int argc, char **argv) {
    if (argc < 2) {
        fmt::print("Expecting at least one argument");
        return -1;
    }
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    mbedtls_sha256_starts(&ctx, 0);
    for (int ii = 1; ii < argc; ++ii) {
        auto a = std::string_view{argv[ii]};
        mbedtls_sha256_update(&ctx, reinterpret_cast<const unsigned char*>(a.data()), a.size());
    }
    unsigned char result[32] = "\0";
    mbedtls_sha256_finish(&ctx, result);
    mbedtls_sha256_free(&ctx);
    std::string sha256;
    for (auto const item: result) {
        fmt::format_to(std::back_inserter(sha256), "{:02x}", item);
    }
    fmt::print("SHA-256: {}\n", sha256);
    return 0;
}
