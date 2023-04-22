#include <boost/integer/common_factor.hpp>
#include <iostream>
#include <iterator>
#include <algorithm>

int main(int argc, char **argv)
{
    if (argc < 3) {
        std::cerr << "2 integer arguments required\n";
        return -1;
    }
    auto a = std::atoi(argv[1]);
    auto b = std::atoi(argv[2]);
    auto result = boost::integer::gcd(a, b);
    std::cout << "gcd of " << a << " and " << b << " is: " << result << '\n';
    return result;
}
