#pragma once

#include <QMainWindow>


class MainWindow : public QMainWindow {
    Q_OBJECT
public:
    MainWindow();
    virtual ~MainWindow() = default;
signals:
    void hey();
};
