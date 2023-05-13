#include <string_view>

#ifdef _WIN32
#ifdef SHARED_EXPORT
#    define SHARED_API __declspec(dllexport)
#elif defined(LIB_IMPORT)
#    define SHARED_API __declspec(dllimport)
#else
#define SHARED_API
#endif
#else
#define SHARED_API
#endif

namespace lib {
    SHARED_API std::string_view get_message() noexcept;
}// namespace lib
