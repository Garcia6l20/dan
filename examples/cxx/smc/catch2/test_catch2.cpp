#include <catch2/catch_all.hpp>

// TEST_CASE("line-commented-test", "[pymake][catch2]") {
//     REQUIRE(true == true);
// }

/*
TEST_CASE("block-commented-test", "[pymake][catch2]") {
    REQUIRE(true == true);
}
*/

TEST_CASE("smc::catch2/test1", "[pymake][catch2]") {
    REQUIRE(true == true);
}

TEST_CASE("smc::catch2/test2") {
    REQUIRE(true == true);
}
