#include <catch2/catch_all.hpp>
#include <spdlog/spdlog.h>

// TEST_CASE("line-commented-test", "[pymake][catch2]") {
//     REQUIRE(true == true);
// }

/*
TEST_CASE("block-commented-test", "[pymake][catch2]") {
    REQUIRE(true == true);
}
*/

TEST_CASE("smc::catch2/test1", "[pymake][catch2]") {
    spdlog::info("smc::catch2/test1");
    REQUIRE(true == true);
}

TEST_CASE("smc::catch2/test2") {
    spdlog::info("smc::catch2/test2");
    REQUIRE(true == true);
}
