#include <lib-config.hpp>
#include <lib.hpp>

#include <string>
#include <string_view>

namespace lib
{
    std::string_view get_message() noexcept
    {
        static std::string greeter;
        if (greeter.empty())
        {
            greeter = "Greethings";
            if constexpr (IS_LINUX)
            {
                greeter += " within linux";
            }
            if constexpr (IS_CLANG)
            {
                greeter += " (CLANG)";
            }
            else if constexpr (IS_GCC)
            {
                greeter += " (GCC)";
            }
            else if constexpr (IS_WIN32)
            {
                greeter += " (WIN32)";
            }
            greeter += " !!!";
        }
        return greeter;
    }
} // namespace lib
