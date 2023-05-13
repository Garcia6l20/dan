#include <lib-config.hpp>
#include <lib.hpp>

namespace lib {
    std::string_view get_message() noexcept {
        if constexpr (IS_LINUX) {
            return "Greethings with Linux !!!";
        } else {
            return "Greethings !!!";
        }
    }
}// namespace lib
