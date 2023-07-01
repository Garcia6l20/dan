#include <vector>
#include <memory>

int main() {
    std::vector<std::unique_ptr<int>> foo;
    std::vector<std::unique_ptr<int>> bar = foo;
    return 0;
}
