#include <test.hpp>

#include <iostream>

#ifndef SIMPLE_GREATER
#error "SIMPLE_GREATER is not defined !"
#endif

namespace simple
{
    void say_hello()
    {
        std::cout << SIMPLE_GREATER << " !\n";
    }
} // namespace simple
